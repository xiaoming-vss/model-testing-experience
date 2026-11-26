"""Requirement workspace orchestration over the existing generation lifecycle."""

from typing import Any

from testing_agent.core.errors import AppError, ErrBadRequest, ErrNotFound, dynamic_error
from testing_agent.models.requirement import Requirement
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.generation_chain import GenerationChainRepository
from testing_agent.repositories.generation_schema import candidate_schema_installed
from testing_agent.repositories.requirement_design import RequirementDesignRepository
from testing_agent.schemas.requirement_design import (
    DesignKind,
    RequirementDesignConfigurationRequest,
)
from testing_agent.services.ai_task_commands import GenerationTaskCommands
from testing_agent.services.ai_task_output import dump_task
from testing_agent.services.ai_task_scope import GenerationAccess
from testing_agent.services.project_access import ProjectAction

LABELS = {
    "requirement_analysis": "需求分析",
    "function": "功能测试",
    "api": "API 测试",
    "ui": "UI 测试",
}


class RequirementDesignService:
    def __init__(
        self,
        repository: RequirementDesignRepository,
        task_repository: AiGenerateTaskRepository,
        access: GenerationAccess,
        commands: GenerationTaskCommands,
    ) -> None:
        self.repository = repository
        self.task_repository = task_repository
        self.access = access
        self.commands = commands

    async def scope(
        self, requirement_id: str, user_id: str, action: ProjectAction = "read"
    ) -> Requirement:
        await self.access.ensure_requirement_access(user_id, requirement_id, action=action)
        requirement = await self.task_repository.get_requirement(requirement_id)
        if requirement is None:
            raise ErrNotFound()
        return requirement

    async def reject_standalone_run(
        self, requirement_id: str, kind: DesignKind, task_id: str, user_id: str
    ) -> None:
        """Validate the caller's task scope, then point them at the generation chain."""
        await self.scope(requirement_id, user_id, action="execute")
        task = await self.access.owned_task(user_id, task_id, kind, action="read")
        if task.requirement_id != requirement_id:
            raise ErrNotFound()
        raise dynamic_error(ErrBadRequest, "请在需求生成链中启动独立阶段")

    async def overview(self, requirement_id: str, user_id: str) -> dict[str, Any]:
        await self.scope(requirement_id, user_id)
        return {
            "tasks": await self.repository.task_summaries(requirement_id),
            "runCounts": await self.repository.run_counts(requirement_id),
            "activeTaskIds": await self.repository.active_task_ids(requirement_id),
        }

    async def history(
        self,
        requirement_id: str,
        kind: DesignKind,
        user_id: str,
        page: int,
        page_size: int,
        pipeline_filter: str,
    ) -> dict[str, Any]:
        await self.scope(requirement_id, user_id)
        return await self.repository.history(requirement_id, kind, page, page_size, pipeline_filter)

    async def configure(
        self,
        requirement_id: str,
        kind: DesignKind,
        body: RequirementDesignConfigurationRequest,
        user_id: str,
    ) -> dict[str, Any]:
        if body.task_id and body.new_configuration:
            raise ErrBadRequest()
        if kind == "api" and body.source_content:
            raise AppError(400, "API 用例生成任务不再接受 OpenAPI/Swagger 文档来源", 400)
        requirement = await self.scope(requirement_id, user_id)
        if not await candidate_schema_installed(self.task_repository.session):
            raise AppError(400, "请先升级候选数据表", 400)
        sprint = await self.task_repository.get_sprint(requirement.sprint_id)
        if sprint is None:
            raise ErrNotFound()
        # Close the authorization snapshot before waiting on the project lock.
        # A member revoked during that wait must not retain access through an old
        # REPEATABLE READ membership snapshot.
        await self.task_repository.commit()
        await self.access.ensure_project_access(user_id, sprint.project_id, action="write")
        await self.access.ensure_sprint_access(user_id, sprint.sprint_id, action="write")
        # Use the run path's project -> sprint -> requirement lock order. The parent
        # lock serializes discovery and creation across requests/processes; create
        # owns the commit. Existing legacy configurations are never merged/deleted.
        locked_requirement = await self.task_repository.get_requirement_for_update(requirement_id)
        if locked_requirement is None:
            raise ErrNotFound()
        requirement = locked_requirement
        sprint = await self.task_repository.get_sprint(requirement.sprint_id)
        if sprint is None:
            raise ErrNotFound()
        bound_task_id = await GenerationChainRepository(
            self.task_repository.session
        ).candidate_chain_task(requirement_id, kind)
        if bound_task_id and (
            body.new_configuration or (body.task_id and body.task_id != bound_task_id)
        ):
            raise AppError(400, "该需求已有当前生成链，请修改现有配置", 400)
        if body.task_id and not bound_task_id:
            raise AppError(400, "旧生成配置不可使用，请创建新的生成链", 400)
        task_id = bound_task_id
        if body.request_id:
            existing = await self.task_repository.get_task_for_update(str(body.request_id))
            if existing is not None:
                if not bound_task_id:
                    raise ErrBadRequest()
                if task_id and task_id != existing.task_id:
                    raise ErrBadRequest()
                task_id = existing.task_id
        if task_id:
            task = await self.access.owned_task(
                user_id, task_id, kind, action="write", current_read=True
            )
            if task.requirement_id != requirement_id:
                raise ErrNotFound()
            changes: dict[str, Any] = {}
            if body.instruction is not None:
                changes["instruction"] = body.instruction
            if kind == "api" and body.interface_ids is not None:
                if not body.interface_ids:
                    raise AppError(400, "请至少选择一个接口", 400)
                changes["interfaceIds"] = body.interface_ids
            if changes:
                return await self.commands.update(
                    kind, task_id, changes, user_id, current_read=True
                )
            return dump_task(task)
        if kind == "api" and not body.interface_ids:
            raise AppError(400, "请至少选择一个接口", 400)
        return await self.commands.create(
            kind,
            sprint.project_id,
            {
                "name": f"{requirement.name} · {LABELS[kind]}",
                "requirementId": requirement_id,
                "sprintId": requirement.sprint_id,
                **(
                    {"interfaceIds": body.interface_ids}
                    if kind == "api"
                    else {"sourceType": "requirement", "sourceContent": ""}
                ),
                "instruction": body.instruction or "",
            },
            user_id,
            task_id=str(body.request_id) if body.request_id else None,
            initialize_candidate_chain=True,
        )
