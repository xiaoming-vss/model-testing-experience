"""Prepare and dispatch UI candidates using one verified frozen source batch."""

# transaction-bound: recheck source, repository and selected cases before dispatch.

from copy import deepcopy
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models.software_repository import SoftwareRepository
from testing_agent.repositories.generation_candidate_storage import candidate_stage_scope
from testing_agent.repositories.generation_root_inputs import lock_ui_repository_cases_source
from testing_agent.schemas.generation_candidates import CandidateRunRequest
from testing_agent.services.generation_application_scope import GenerationApplicationScope
from testing_agent.services.generation_candidate_dispatch import (
    dispatch_candidate_stage,
    replay_candidate_stage,
)
from testing_agent.services.generation_chain import GenerationChainService
from testing_agent.services.generation_document_preparation import (
    lock_prepared_requirement_root,
    prepare_requirement_document,
)
from testing_agent.services.generation_ui_candidate_source import read_selected_ui_surface_source
from testing_agent.services.personal_authorization import require_personal_connection
from testing_agent.services.repository_profile_current import RepositoryProfileCurrent


class UiCandidateDispatch:
    """Coordinate remote source preparation and a locked candidate dispatch.

    This request-scoped boundary commits on success. The caller owns rollback and
    maps source and root verification errors to the public API.
    """

    def __init__(self, chain: GenerationChainService) -> None:
        self.chain = chain
        self.session = chain.tasks.session
        self.scope = GenerationApplicationScope(chain, action="execute")

    async def _task(self, requirement_id: str, stage: str):
        scoped = await candidate_stage_scope(
            self.session, requirement_id=requirement_id, kind="ui", stage=stage
        )
        if scoped is None:
            raise dynamic_error(ErrBadRequest, "当前 UI 生成链尚未初始化")
        return scoped[2]

    async def run(
        self, *, requirement_id: str, stage: str, request: CandidateRunRequest, actor_id: str
    ) -> tuple[str, bool]:
        if self.chain.ui_sources is None:
            raise dynamic_error(ErrBadRequest, "UI 仓库源码解析未配置")
        if request.request_id is None:
            raise ErrBadRequest()
        parent = await self.scope.authorize(requirement_id, actor_id)
        await require_personal_connection(
            self.session, actor_id, "llm", request.connection_id, parent.project_id
        )
        await self.session.rollback()
        await self.scope.lock_parents(requirement_id, actor_id, parent)
        task = await self._task(requirement_id, stage)
        await require_personal_connection(
            self.session, actor_id, "llm", request.connection_id, parent.project_id
        )
        replay = await replay_candidate_stage(
            self.session, task=task, kind="ui", stage=stage, request=request, actor_id=actor_id
        )
        if replay is not None:
            attempt_id = replay.attempt.id
            await self.session.rollback()
            return attempt_id, True
        await self.session.rollback()

        current_profile = None
        prepared_document = None
        selected = None
        if stage == "ui_surface":
            if not request.source_repository_id or self.chain.files is None:
                raise dynamic_error(ErrBadRequest, "请选择当前画像中的前端仓库")
            if request.function_case_ids is not None and (
                not request.function_case_ids
                or len(set(request.function_case_ids)) != len(request.function_case_ids)
            ):
                raise dynamic_error(ErrBadRequest, "请选择当前需求下至少一条正式功能用例")
            reader = RepositoryProfileCurrent(self.chain)
            current_profile = await reader.read(requirement_id=requirement_id, actor_id=actor_id)
            if current_profile is None:
                raise dynamic_error(ErrBadRequest, "请先采用仓库画像")
            if request.source_profile_candidate_id and (
                request.source_profile_candidate_id != current_profile.candidate_id
            ):
                raise SourceClosureError("concurrent_change")
            resolved = await self.chain.ui_sources.resolve_current(
                current=current_profile,
                project_id=parent.project_id,
                user_id=actor_id,
                repository_id=request.source_repository_id,
                commit_mode=request.source_commit_mode,
                gitlab_connection_id=request.gitlab_connection_id,
            )
            await self.session.rollback()
            prepared_document = await prepare_requirement_document(
                self.session, requirement_id=requirement_id, files=self.chain.files
            )
            await self.session.rollback()
            source: dict[str, Any] = {
                "sourceKind": "repository",
                "sourceType": "repository",
                "sourceContent": "",
                "sourceProfileCandidateId": current_profile.candidate_id,
                "sourceProfileSnapshotId": current_profile.snapshot_id,
                "sourceRepository": resolved.repository,
                "bindings": [resolved.binding],
                "uiWorkflowVersion": "ui_three_stage/1.0",
                "uiSourceBatchId": str(uuid4()),
            }
        else:
            if (
                request.refresh_inputs
                or request.function_case_ids is not None
                or request.source_repository_id
                or request.source_profile_candidate_id
            ):
                raise ErrBadRequest()
            selected = await read_selected_ui_surface_source(
                self.session, requirement_id=requirement_id, request=request
            )
            source = deepcopy(selected.source)
            repository = source.get("sourceRepository")
            bindings = source.get("bindings")
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
                project_id=parent.project_id,
                user_id=actor_id,
                gitlab_connection_id=request.gitlab_connection_id,
            )
            source["bindings"] = [rebound]
            await self.session.rollback()

        await self.scope.lock_parents(requirement_id, actor_id, parent)
        task = await self._task(requirement_id, stage)
        await require_personal_connection(
            self.session, actor_id, "llm", request.connection_id, parent.project_id
        )
        replay = await replay_candidate_stage(
            self.session, task=task, kind="ui", stage=stage, request=request, actor_id=actor_id
        )
        if replay is not None:
            attempt_id = replay.attempt.id
            await self.session.rollback()
            return attempt_id, True
        if current_profile is not None:
            assert prepared_document is not None
            document_root = await lock_prepared_requirement_root(
                self.session, prepared=prepared_document
            )
            await RepositoryProfileCurrent(self.chain).lock_verified(
                requirement_id=requirement_id,
                document_root=document_root,
                source_id=current_profile.candidate_id,
                expected=current_profile,
            )
        else:
            assert selected is not None
            verified = await read_selected_ui_surface_source(
                self.session, requirement_id=requirement_id, request=request
            )
            if verified != selected:
                raise SourceClosureError("concurrent_change")

        binding = source["bindings"][0]
        repository_id = str(binding.get("softwareRepositoryId") or binding.get("bindingId") or "")
        repository = await self.session.scalar(
            select(SoftwareRepository)
            .where(SoftwareRepository.software_repository_id == repository_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if repository is None or repository.project_id != parent.project_id:
            raise SourceClosureError("source_stale")
        access = await self.chain.ui_sources.resolve_binding_access(
            parent.project_id, actor_id, binding, gitlab_connection_id=binding["connectionId"]
        )
        source_repository = source.get("sourceRepository")
        if (
            access.connection_id != binding["connectionId"]
            or not isinstance(source_repository, dict)
            or access.base_url.rstrip("/").lower()
            != str(source_repository.get("instanceUrl") or "").rstrip("/").lower()
        ):
            raise SourceClosureError("concurrent_change")
        source.update(
            {
                "taskId": task.task_id,
                "taskType": task.task_type,
                "name": task.name,
                "projectId": task.project_id,
                "sprintId": task.sprint_id,
                "requirementId": requirement_id,
                "instruction": request.instruction or "",
                "generationChainManaged": True,
            }
        )
        if stage == "ui_surface":
            cases = await self.chain.tasks.list_ui_source_cases(
                requirement_id, request.function_case_ids
            )
            if not cases or (
                request.function_case_ids is not None
                and {case["caseId"] for case in cases} != set(request.function_case_ids)
            ):
                raise dynamic_error(ErrBadRequest, "请选择当前需求下至少一条正式功能用例")
            source["functionalCases"] = cases
        root, cases = await lock_ui_repository_cases_source(
            self.session, task=task, frozen_source=source
        )
        source["functionalCases"] = cases
        result = await dispatch_candidate_stage(
            self.session,
            task=task,
            kind="ui",
            stage=stage,
            request=request,
            actor_id=actor_id,
            source=source,
            current_root_hashes={root.key: root.content_hash},
            direct_roots=(root,),
        )
        attempt_id = result.attempt.id
        await self.session.commit()
        return attempt_id, result.replayed
