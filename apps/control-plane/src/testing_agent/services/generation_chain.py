"""Requirement generation chain access and candidate-based views."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from testing_agent.core.errors import ErrBadRequest, ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.domain.ai_tasks import task_type_for
from testing_agent.domain.generation_chain import (
    CHAIN_KINDS,
    stage_names,
)
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.generation_chain import GenerationChainRepository
from testing_agent.schemas.generation_chain import (
    GenerationChainOverview,
    GenerationChainView,
)
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.ai_task_access import GenerationImportContext
from testing_agent.services.ai_task_scope import GenerationAccess
from testing_agent.services.api_generate_import import ApiCandidateImporter
from testing_agent.services.project_access import ProjectAction
from testing_agent.services.stage_storage.chain_view import build_chain_view
from testing_agent.services.stored_file import StoredFileService
from testing_agent.services.ui_generation_source import UiGenerationSourceService


class GenerationChainService:
    def __init__(
        self,
        *,
        repository: GenerationChainRepository,
        tasks: AiGenerateTaskRepository,
        access: GenerationAccess,
        files: StoredFileService | None,
        imports: GenerationImportContext,
        api_importer: ApiCandidateImporter,
        ui_sources: UiGenerationSourceService | None = None,
        id_factory: Callable[[], str] = new_id,
    ) -> None:
        self.repository = repository
        self.tasks = tasks
        self.access = access
        self.files = files
        self.imports = imports
        self.api_importer = api_importer
        self.ui_sources = ui_sources
        self.new_id = id_factory

    async def scope(self, requirement_id: str, user_id: str, action: ProjectAction = "read"):
        await self.access.ensure_requirement_access(user_id, requirement_id, action=action)
        requirement = await self.tasks.get_requirement(requirement_id)
        if requirement is None:
            raise ErrNotFound()
        return requirement

    async def optional_task(
        self, requirement_id: str, kind: DesignKind, user_id: str
    ) -> AiGenerateTask | None:
        await self.scope(requirement_id, user_id)
        bound_task_id = await self.repository.candidate_chain_task(requirement_id, kind)
        task = await self.tasks.get_task(bound_task_id) if bound_task_id else None
        if bound_task_id and (task is None or task.task_type != task_type_for(kind)):
            raise ErrNotFound()
        if task is not None:
            if task.requirement_id != requirement_id:
                raise ErrNotFound()
            await self.access.validate_task_scope(task)
        return task

    async def overview(self, requirement_id: str, user_id: str) -> GenerationChainOverview:
        """Return every configured chain for the requirement panorama."""
        await self.scope(requirement_id, user_id)
        chains = []
        for item in CHAIN_KINDS:
            kind = cast(DesignKind, item)
            bound_task_id = await self.repository.candidate_chain_task(requirement_id, kind)
            task = await self.tasks.get_task(bound_task_id) if bound_task_id else None
            if bound_task_id and (task is None or task.task_type != task_type_for(kind)):
                raise ErrNotFound()
            if task is not None:
                if task.requirement_id != requirement_id:
                    raise ErrNotFound()
                await self.access.validate_task_scope(task)
            chains.append(
                await build_chain_view(self.tasks.session, requirement_id, kind, task, detail=False)
            )
        return GenerationChainOverview(chains=chains)

    async def chain_view(
        self, requirement_id: str, kind: DesignKind, user_id: str, *, detail: bool
    ) -> GenerationChainView:
        task = await self.optional_task(requirement_id, kind, user_id)
        return await build_chain_view(self.tasks.session, requirement_id, kind, task, detail=detail)

    def validate_stage(self, kind: DesignKind, stage: str) -> None:
        if kind not in (*CHAIN_KINDS, "repository_profile") or stage not in stage_names(kind):
            raise ErrBadRequest()
