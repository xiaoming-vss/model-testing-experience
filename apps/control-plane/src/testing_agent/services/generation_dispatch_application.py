"""Authorized candidate-generation boundary for requirement-linked chains."""

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.generation_chain import HISTORICAL_STAGES
from testing_agent.domain.generation_root_fingerprints import IncompleteRootInput
from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.repositories.generation_candidate_storage import candidate_stage_scope
from testing_agent.repositories.generation_current_chain import ensure_empty_slot
from testing_agent.repositories.generation_root_inputs import lock_api_generation_source
from testing_agent.repositories.standalone_execution import lock_or_create_stage
from testing_agent.schemas.generation_candidates import CandidateRunRequest
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_application_scope import GenerationApplicationScope
from testing_agent.services.generation_candidate_dispatch import (
    dispatch_candidate_stage,
    replay_candidate_stage,
)
from testing_agent.services.generation_chain import GenerationChainService
from testing_agent.services.generation_document_preparation import (
    PreparedRequirementDocument,
    bind_prepared_document_source,
    lock_prepared_requirement_root,
    prepare_requirement_document,
)
from testing_agent.services.generation_source_errors import closure_error, source_error
from testing_agent.services.personal_authorization import require_personal_connection


@dataclass(frozen=True)
class CandidateRunReceipt:
    request_id: str
    attempt_id: str
    replayed: bool


class CandidateDispatchApplication:
    """Prepare trusted inputs and enqueue one candidate with actor authorization.

    This top-level operation owns commit and rollback. It requires a fresh
    request-scoped session without unrelated writes.
    """

    def __init__(self, chain: GenerationChainService) -> None:
        self.chain = chain
        self.session = chain.tasks.session
        self.scope = GenerationApplicationScope(chain, action="execute")

    async def _task(
        self, requirement_id: str, kind: DesignKind, stage: str, *, ensure_stage: bool = False
    ) -> AiGenerateTask:
        scoped = await candidate_stage_scope(
            self.session, requirement_id=requirement_id, kind=kind, stage=stage
        )
        if scoped is None and stage in HISTORICAL_STAGES:
            scoped = await candidate_stage_scope(
                self.session, requirement_id=requirement_id, kind=kind, stage="extracting_text"
            )
            if scoped is not None and ensure_stage:
                chain_id, _, task = scoped
                allocated, _ = await lock_or_create_stage(self.session, task.task_id, stage)
                await ensure_empty_slot(self.session, chain_id=chain_id, stage_id=allocated.id)
        if scoped is None:
            raise dynamic_error(ErrBadRequest, "当前生成链尚未初始化")
        return scoped[2]

    async def _replay(
        self,
        task: AiGenerateTask,
        kind: DesignKind,
        stage: str,
        request: CandidateRunRequest,
        actor_id: str,
    ) -> CandidateRunReceipt | None:
        replay = await replay_candidate_stage(
            self.session, task=task, kind=kind, stage=stage, request=request, actor_id=actor_id
        )
        if replay is None:
            return None
        return CandidateRunReceipt(str(request.request_id), replay.attempt.id, True)

    async def run(
        self,
        *,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        request: CandidateRunRequest,
        actor_id: str,
    ) -> CandidateRunReceipt:
        """Dispatch using only locked current roots and explicit candidate selections."""
        try:
            self.chain.validate_stage(kind, stage)
            if request.request_id is None:
                request = request.model_copy(update={"request_id": uuid4()})
            if kind == "ui":
                from testing_agent.services.generation_ui_dispatch import UiCandidateDispatch

                attempt_id, replayed = await UiCandidateDispatch(self.chain).run(
                    requirement_id=requirement_id, stage=stage, request=request, actor_id=actor_id
                )
                return CandidateRunReceipt(str(request.request_id), attempt_id, replayed)
            parent = await self.scope.authorize(requirement_id, actor_id)
            await require_personal_connection(
                self.session, actor_id, "llm", request.connection_id, parent.project_id
            )
            await self.session.rollback()
            await self.scope.lock_parents(requirement_id, actor_id, parent)
            task = await self._task(requirement_id, kind, stage)
            await require_personal_connection(
                self.session, actor_id, "llm", request.connection_id, parent.project_id
            )
            replay = await self._replay(task, kind, stage, request, actor_id)
            if replay is not None:
                await self.session.rollback()
                return replay
            await self.session.rollback()
            prepared: PreparedRequirementDocument | None = None
            if kind in {"requirement_analysis", "function"}:
                if self.chain.files is None:
                    raise dynamic_error(ErrBadRequest, "需求文件存储不可用")
                prepared = await prepare_requirement_document(
                    self.session, requirement_id=requirement_id, files=self.chain.files
                )
                await self.session.rollback()
            await self.scope.lock_parents(requirement_id, actor_id, parent)
            task = await self._task(requirement_id, kind, stage, ensure_stage=True)
            await require_personal_connection(
                self.session, actor_id, "llm", request.connection_id, parent.project_id
            )
            replay = await self._replay(task, kind, stage, request, actor_id)
            if replay is not None:
                await self.session.rollback()
                return replay
            source: dict[str, Any] = {
                "taskId": task.task_id,
                "taskType": task.task_type,
                "name": task.name,
                "projectId": task.project_id,
                "sprintId": task.sprint_id,
                "requirementId": requirement_id,
                "sourceContent": "",
                "instruction": request.instruction or "",
                "generationChainManaged": True,
            }
            if kind in {"requirement_analysis", "function"}:
                assert prepared is not None
                root = await lock_prepared_requirement_root(self.session, prepared=prepared)
                if kind == "requirement_analysis":
                    source.update(
                        {
                            "documentFileId": prepared.document.file_id,
                            "documentHash": prepared.document.sha256,
                            "documentType": prepared.document_type,
                            "documentFilename": prepared.document.filename,
                            "workflowVersion": 2,
                        }
                    )
                    source = bind_prepared_document_source(
                        source=source, prepared=prepared, root=root
                    )
                else:
                    source["sourceType"] = "requirement"
            elif kind == "api":
                root, repositories, interfaces = await lock_api_generation_source(
                    self.session, task=task
                )
                requirement = await self.chain.tasks.get_requirement(requirement_id)
                if requirement is None:
                    raise SourceClosureError("source_unknown")
                source.update(
                    {
                        "sourceType": "interface_library",
                        "interfaces": interfaces,
                        "softwareRepositories": repositories,
                        "apiWorkflowVersion": "api_three_stage/1.0",
                        "requirement": {
                            "requirementId": requirement_id,
                            "name": requirement.name,
                            "instruction": request.instruction or "",
                        },
                    }
                )
                source.pop("sourceContent", None)
            else:
                raise SourceClosureError("source_unknown")
            result = await dispatch_candidate_stage(
                self.session,
                task=task,
                kind=kind,
                stage=stage,
                request=request,
                actor_id=actor_id,
                source=source,
                current_root_hashes={root.key: root.content_hash},
                direct_roots=(root,),
            )
            receipt = CandidateRunReceipt(
                str(request.request_id), result.attempt.id, result.replayed
            )
            await self.session.commit()
            return receipt
        except IncompleteRootInput as exc:
            await self.session.rollback()
            raise source_error("source_unknown") from exc
        except SourceClosureError as exc:
            await self.session.rollback()
            raise closure_error(exc) from exc
        except Exception:
            await self.session.rollback()
            raise
