"""Authorize, freeze and dispatch a new candidate revision."""

# transaction-bound: queue, source locks, images and attempt commit together.

from copy import deepcopy
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.generation_root_fingerprints import IncompleteRootInput
from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.domain.request_identity import request_signature
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.generation_candidates import AiGenerationCandidate
from testing_agent.models.software_repository import SoftwareRepository
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.generation_candidate_storage import candidate_stage_scope
from testing_agent.schemas.generation_candidates import (
    CandidateAdoptRequest,
    CandidateRevisionRequest,
)
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_adoption_roots import lock_adoption_roots
from testing_agent.services.generation_application_scope import GenerationApplicationScope
from testing_agent.services.generation_chain import GenerationChainService
from testing_agent.services.generation_dispatch_application import CandidateRunReceipt
from testing_agent.services.generation_document_preparation import prepare_requirement_document
from testing_agent.services.generation_revision_preparation import (
    attach_prepared_revision_uploads,
    prepare_revision_uploads,
)
from testing_agent.services.generation_revision_snapshot import build_revision_snapshot
from testing_agent.services.generation_source_errors import closure_error, source_error
from testing_agent.services.generation_source_resolution import (
    ResolvedCandidateSelection,
    lock_candidate_source_closure,
)
from testing_agent.services.personal_authorization import require_personal_connection
from testing_agent.services.stage_storage.dispatch import (
    dispatch_stage_attempt,
    replay_stage_attempt,
    reserve_worker_identity,
)


class CandidateRevisionApplication:
    """Use the selected candidate's frozen branch, never a newly selected upstream."""

    def __init__(self, chain: GenerationChainService) -> None:
        self.chain = chain
        self.session = chain.tasks.session
        self.scope = GenerationApplicationScope(chain, action="execute")

    async def run(
        self,
        *,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        candidate_id: str,
        request: CandidateRevisionRequest,
        actor_id: str,
    ) -> CandidateRunReceipt:
        signature = request_signature(
            "generation-candidate-revise",
            {
                "requirementId": requirement_id,
                "kind": kind,
                "stage": stage,
                "candidateId": candidate_id,
                "actorId": actor_id,
                "request": request.model_dump(mode="json", by_alias=True, exclude={"request_id"}),
            },
        )
        try:
            self.chain.validate_stage(kind, stage)
            if kind != "ui" and request.gitlab_connection_id:
                raise ErrBadRequest()
            if kind == "ui" and request.attachment_file_ids:
                raise dynamic_error(ErrBadRequest, "UI 阶段暂不支持附加优化图片，请移除后重试")
            parent_scope = await self.scope.authorize(requirement_id, actor_id)
            await require_personal_connection(
                self.session, actor_id, "llm", request.connection_id, parent_scope.project_id
            )
            await self.session.rollback()
            await self.scope.lock_parents(requirement_id, actor_id, parent_scope)
            scoped = await candidate_stage_scope(
                self.session, requirement_id=requirement_id, kind=kind, stage=stage
            )
            if scoped is None:
                raise SourceClosureError("source_unknown")
            initial_scope = scoped[:2]
            await require_personal_connection(
                self.session, actor_id, "llm", request.connection_id, parent_scope.project_id
            )
            replay = await self._replay(scoped[2], stage, request, actor_id, signature)
            if replay is not None:
                await self.session.rollback()
                return replay
            candidate = await self.session.scalar(
                select(AiGenerationCandidate).where(
                    AiGenerationCandidate.candidate_id == candidate_id,
                    AiGenerationCandidate.chain_id == scoped[0],
                    AiGenerationCandidate.stage_id == scoped[1],
                )
            )
            if (
                candidate is None
                or candidate.candidate_token != request.expected_candidate_token
                or candidate.current_attempt_id != request.expected_attempt_id
            ):
                raise SourceClosureError("concurrent_change")
            if not isinstance(candidate.source_snapshot_json, dict):
                raise SourceClosureError("source_unknown")
            snapshot_id = candidate.snapshot_id
            frozen_source = deepcopy(candidate.source_snapshot_json.get("source"))
            await self.session.rollback()
            prepared_document = None
            if kind in {"requirement_analysis", "function"}:
                if self.chain.files is None:
                    raise dynamic_error(ErrBadRequest, "需求文件存储不可用")
                prepared_document = await prepare_requirement_document(
                    self.session, requirement_id=requirement_id, files=self.chain.files
                )
                await self.session.rollback()
            prepared_uploads = None
            if request.attachment_file_ids:
                if self.chain.files is None:
                    raise dynamic_error(ErrBadRequest, "文件存储不可用")
                prepared_uploads = await prepare_revision_uploads(
                    self.session,
                    files=self.chain.files,
                    project_id=parent_scope.project_id,
                    actor_id=actor_id,
                    file_ids=request.attachment_file_ids,
                )
                await self.session.rollback()
            rebound = None
            if kind == "ui":
                if self.chain.ui_sources is None or not isinstance(frozen_source, dict):
                    raise SourceClosureError("source_unknown")
                repository = frozen_source.get("sourceRepository")
                bindings = frozen_source.get("bindings")
                if (
                    not isinstance(repository, dict)
                    or not isinstance(bindings, list)
                    or len(bindings) != 1
                    or not isinstance(bindings[0], dict)
                ):
                    raise SourceClosureError("source_unknown")
                rebound = await self.chain.ui_sources.rebind_frozen(
                    repository=repository,
                    binding=bindings[0],
                    project_id=parent_scope.project_id,
                    user_id=actor_id,
                    gitlab_connection_id=request.gitlab_connection_id,
                )
                await self.session.rollback()

            await self.scope.lock_parents(requirement_id, actor_id, parent_scope)
            scoped = await candidate_stage_scope(
                self.session, requirement_id=requirement_id, kind=kind, stage=stage
            )
            if scoped is None or scoped[:2] != initial_scope:
                raise SourceClosureError("concurrent_change")
            await require_personal_connection(
                self.session, actor_id, "llm", request.connection_id, parent_scope.project_id
            )
            replay = await self._replay(scoped[2], stage, request, actor_id, signature)
            if replay is not None:
                await self.session.rollback()
                return replay
            attempt_id = str(uuid4())
            worker, reused = await reserve_worker_identity(
                self.session, scoped[2], str(request.request_id), attempt_id
            )
            if reused:
                replayed_attempt = await replay_stage_attempt(
                    self.session,
                    worker=worker,
                    task=scoped[2],
                    stage_name=stage,
                    actor_id=actor_id,
                    operation="revise",
                    signature=signature,
                )
                await self.session.rollback()
                return CandidateRunReceipt(str(request.request_id), replayed_attempt.id, True)
            stage_row = await self.session.scalar(
                select(AiGenerationStage)
                .where(AiGenerationStage.id == scoped[1])
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if stage_row is None or stage_row.active_attempt_id:
                raise dynamic_error(ErrBadRequest, "阶段正在运行")
            root_request = CandidateAdoptRequest(
                action="adopt",
                candidate_id=candidate_id,
                expected_candidate_token=request.expected_candidate_token,
                expected_attempt_id=request.expected_attempt_id,
                expected_current_token="unused",
                request_id=request.request_id,
            )
            roots = await lock_adoption_roots(
                self.session,
                requirement_id=requirement_id,
                kind=kind,
                stage=stage,
                request=root_request,
                prepared_document=prepared_document,
            )
            await lock_candidate_source_closure(
                self.session,
                requirement_id=requirement_id,
                selections=(
                    ResolvedCandidateSelection(
                        kind, stage, candidate_id, snapshot_id, request.expected_candidate_token
                    ),
                ),
                required_stages=frozenset({(kind, stage)}),
                current_root_hashes=roots,
            )
            candidate = await self.session.scalar(
                select(AiGenerationCandidate)
                .where(AiGenerationCandidate.candidate_id == candidate_id)
                .execution_options(populate_existing=True)
            )
            if (
                candidate is None
                or candidate.current_attempt_id != request.expected_attempt_id
                or not isinstance(candidate.source_snapshot_json, dict)
                or candidate.source_snapshot_json.get("source") != frozen_source
            ):
                raise SourceClosureError("concurrent_change")
            if rebound is not None:
                await self._verify_ui_access(
                    parent_scope.project_id, actor_id, frozen_source, rebound
                )
            attachments: tuple[dict[str, str], ...] = ()
            hashes: dict[str, str] = {}
            if prepared_uploads is not None:
                assert self.chain.files is not None
                attachments, hashes = await attach_prepared_revision_uploads(
                    self.session,
                    files=self.chain.files,
                    prepared=prepared_uploads,
                    actor_id=actor_id,
                    project_id=parent_scope.project_id,
                    attempt_id=attempt_id,
                )
            snapshot = build_revision_snapshot(
                candidate=candidate,
                kind=kind,
                stage=stage,
                request=request,
                signature=signature,
                attempt_id=attempt_id,
                actor_id=actor_id,
                attachments=attachments,
                attachment_hashes=hashes,
                verified_ui_binding=rebound,
            )
            attempt, replayed = await dispatch_stage_attempt(
                self.session,
                task=scoped[2],
                stage_id=scoped[1],
                request_id=str(request.request_id),
                actor_id=actor_id,
                input_snapshot=snapshot,
                operation="revise",
                expected_attempt_id=request.expected_attempt_id,
                revision_instruction=request.instruction,
                attempt_id=attempt_id,
                reserved_worker=worker,
                allow_multiple_candidates=True,
            )
            await self.session.commit()
            return CandidateRunReceipt(str(request.request_id), attempt.id, replayed)
        except IncompleteRootInput as exc:
            await self.session.rollback()
            raise source_error("source_unknown") from exc
        except SourceClosureError as exc:
            await self.session.rollback()
            raise closure_error(exc) from exc
        except Exception:
            await self.session.rollback()
            raise

    async def _replay(
        self,
        task: AiGenerateTask,
        stage: str,
        request: CandidateRevisionRequest,
        actor_id: str,
        signature: str,
    ) -> CandidateRunReceipt | None:
        worker = await self.session.scalar(
            select(WorkerTask).where(
                WorkerTask.domain == "ai", WorkerTask.task_id == str(request.request_id)
            )
        )
        if worker is None:
            return None
        attempt = await replay_stage_attempt(
            self.session,
            worker=worker,
            task=task,
            stage_name=stage,
            actor_id=actor_id,
            operation="revise",
            signature=signature,
        )
        return CandidateRunReceipt(str(request.request_id), attempt.id, True)

    async def _verify_ui_access(
        self, project_id: str, actor_id: str, source: Any, binding: dict[str, Any]
    ) -> None:
        if self.chain.ui_sources is None or not isinstance(source, dict):
            raise SourceClosureError("source_unknown")
        repository = source.get("sourceRepository")
        repository_id = str(binding.get("softwareRepositoryId") or binding.get("bindingId") or "")
        row = await self.session.scalar(
            select(SoftwareRepository)
            .where(SoftwareRepository.software_repository_id == repository_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None or row.project_id != project_id:
            raise SourceClosureError("source_stale")
        access = await self.chain.ui_sources.resolve_binding_access(
            project_id, actor_id, binding, gitlab_connection_id=binding["connectionId"]
        )
        if (
            access.connection_id != binding["connectionId"]
            or not isinstance(repository, dict)
            or access.base_url.rstrip("/").lower()
            != str(repository.get("instanceUrl") or "").rstrip("/").lower()
        ):
            raise SourceClosureError("concurrent_change")
