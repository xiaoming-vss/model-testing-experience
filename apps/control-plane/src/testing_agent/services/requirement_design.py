"""Requirement workspace orchestration over the existing generation lifecycle."""

from typing import Any
from urllib.parse import urlsplit

import yaml

from testing_agent.core.errors import AppError, ErrBadRequest, ErrNotFound
from testing_agent.models.requirement import Requirement
from testing_agent.repositories.requirement_design import RequirementDesignRepository
from testing_agent.schemas.requirement_design import (
    DesignKind,
    RequirementDesignConfigurationRequest,
    RequirementDesignRunRequest,
)
from testing_agent.services.ai_generate_task import AiGenerateTaskService
from testing_agent.services.ai_task_output import dump_task, requirement_source_content
from testing_agent.services.project_access import ProjectAction

LABELS = {
    "requirement_analysis": "需求分析",
    "function": "功能测试",
    "api": "API 测试",
    "ui": "UI 测试",
}


def has_function_generation_input(requirement: Requirement) -> bool:
    # Use the same enhanced-text parser as run snapshots, including legacy Markdown.
    # The original attachment alone is not sufficient input.
    try:
        return bool(requirement_source_content(requirement).strip())
    except AppError:
        return False


def validate_openapi_source(source: str) -> None:
    parsed_url = urlsplit(source.strip())
    if parsed_url.scheme in {"http", "https"} and parsed_url.hostname:
        return  # Existing URL configurations remain supported by the API worker.
    try:
        document = yaml.safe_load(source)
    except yaml.YAMLError as exc:
        raise AppError(400, "OpenAPI/Swagger 文档不是合法 JSON 或 YAML", 400) from exc
    if not isinstance(document, dict) or not (
        isinstance(document.get("openapi") or document.get("swagger"), str)
        and isinstance(document.get("paths"), dict)
    ):
        raise AppError(400, "请提供包含 openapi/swagger 版本和 paths 的接口文档", 400)


class RequirementDesignService:
    def __init__(self, tasks: AiGenerateTaskService):
        self.tasks = tasks
        self.repository = RequirementDesignRepository(tasks.repository.session)

    async def scope(
        self, requirement_id: str, user_id: str, action: ProjectAction = "read"
    ) -> Requirement:
        await self.tasks.ensure_requirement_access(user_id, requirement_id, action=action)
        requirement = await self.tasks.repository.get_requirement(requirement_id)
        if requirement is None:
            raise ErrNotFound()
        return requirement

    async def overview(self, requirement_id: str, user_id: str) -> dict[str, Any]:
        requirement = await self.scope(requirement_id, user_id)
        return {
            "tasks": await self.repository.task_summaries(requirement_id),
            "runCounts": await self.repository.run_counts(requirement_id),
            "activeTaskIds": await self.repository.active_task_ids(requirement_id),
            "adoptedUnderstanding": has_function_generation_input(requirement),
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
        if kind == "api" and body.source_content is not None:
            validate_openapi_source(body.source_content)
        if body.task_id and body.new_configuration:
            raise ErrBadRequest()
        requirement = await self.scope(requirement_id, user_id)
        sprint = await self.tasks.repository.get_sprint(requirement.sprint_id)
        if sprint is None:
            raise ErrNotFound()
        # Close the authorization snapshot before waiting on the project lock.
        # A member revoked during that wait must not retain access through an old
        # REPEATABLE READ membership snapshot.
        await self.tasks.repository.commit()
        await self.tasks.ensure_project_access(user_id, sprint.project_id, action="write")
        await self.tasks.ensure_sprint_access(user_id, sprint.sprint_id, action="write")
        # Use the run path's project -> sprint -> requirement lock order. The parent
        # lock serializes discovery and creation across requests/processes; create
        # owns the commit. Existing legacy configurations are never merged/deleted.
        locked_requirement = await self.tasks.repository.get_requirement_for_update(requirement_id)
        if locked_requirement is None:
            raise ErrNotFound()
        requirement = locked_requirement
        sprint = await self.tasks.repository.get_sprint(requirement.sprint_id)
        if sprint is None:
            raise ErrNotFound()
        task_id = body.task_id
        if body.request_id:
            existing = await self.tasks.repository.get_task_for_update(str(body.request_id))
            if existing is not None:
                if task_id and task_id != existing.task_id:
                    raise ErrBadRequest()
                task_id = existing.task_id
        if not task_id and not body.new_configuration:
            task_id = await self.repository.configuration_task_id(requirement_id, kind)
        if task_id:
            task = await self.tasks.owned_task(
                user_id, task_id, kind, action="write", current_read=True
            )
            if task.requirement_id != requirement_id:
                raise ErrNotFound()
            changes: dict[str, Any] = {}
            if body.instruction is not None:
                changes["instruction"] = body.instruction
            if kind == "api" and body.source_content is not None:
                if not body.source_content.strip():
                    raise AppError(400, "请提供 OpenAPI/Swagger 文档", 400)
                changes.update(sourceContent=body.source_content, sourceType="openapi")
            if changes:
                return await self.tasks.update(kind, task_id, changes, user_id, current_read=True)
            archive = (
                await self.tasks.source_archive_repository.get_source_archive(task_id)
                if kind == "ui"
                else None
            )
            return dump_task(task, archive)
        if kind == "api" and not (body.source_content or "").strip():
            raise AppError(400, "请提供 OpenAPI/Swagger 文档", 400)
        return await self.tasks.create(
            kind,
            sprint.project_id,
            {
                "name": f"{requirement.name} · {LABELS[kind]}",
                "requirementId": requirement_id,
                "sprintId": requirement.sprint_id,
                "sourceType": "openapi" if kind == "api" else "requirement",
                "sourceContent": body.source_content or "",
                "instruction": body.instruction or "",
            },
            user_id,
            task_id=str(body.request_id) if body.request_id else None,
        )

    async def start(
        self,
        requirement_id: str,
        kind: DesignKind,
        body: RequirementDesignRunRequest,
        user_id: str,
    ) -> dict[str, Any]:
        requirement = await self.scope(requirement_id, user_id)
        sprint = await self.tasks.repository.get_sprint(requirement.sprint_id)
        if sprint is None:
            raise ErrNotFound()
        await self.tasks.repository.commit()
        await self.tasks.ensure_project_access(user_id, sprint.project_id, action="execute")
        task = await self.tasks.owned_task(user_id, body.task_id, kind, action="read")
        if task.requirement_id != requirement_id:
            raise ErrNotFound()
        if kind == "function" and not has_function_generation_input(requirement):
            raise AppError(400, "请先补充有效的需求增强文本，再生成功能用例", 400)
        if kind == "api" and not task.source_content.strip():
            raise AppError(400, "请先配置 OpenAPI/Swagger 文档", 400)
        return await self.tasks.run(
            kind,
            task.task_id,
            body.model_dump(by_alias=True, exclude_none=True, exclude={"task_id", "request_id"}),
            user_id,
            request_id=str(body.request_id),
        )
