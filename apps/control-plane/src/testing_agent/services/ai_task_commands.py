from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from testing_agent.core.enums import RUN_ACTIVE_STATUSES
from testing_agent.core.errors import (
    ErrAiGenerateTaskRunRunning,
    ErrBadRequest,
    ErrNotFound,
)
from testing_agent.core.sid import new_id
from testing_agent.domain.ai_tasks import (
    task_type_for,
)
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.ai_generate_task_source_archive import (
    AiGenerateTaskSourceArchiveRepository,
)
from testing_agent.services.ai_task_output import (
    dump_task,
)
from testing_agent.services.ai_task_scope import GenerationAccess
from testing_agent.services.resource_deletion import ResourceDeletion, SqlResourceDeletion


class GenerationTaskCommands:
    """Task lifecycle commands; each public mutation owns its existing commit."""

    def __init__(
        self,
        repository: AiGenerateTaskRepository,
        source_archive_repository: AiGenerateTaskSourceArchiveRepository,
        access: GenerationAccess,
        *,
        deletion: ResourceDeletion | None = None,
        id_factory: Callable[[], str] = new_id,
    ) -> None:
        self.repository = repository
        self.source_archive_repository = source_archive_repository
        self.access = access
        self.deletion = deletion or SqlResourceDeletion()
        self.id_factory = id_factory

    async def create(
        self,
        kind: str,
        project_id: str,
        body: dict[str, Any],
        user_id: str,
        *,
        task_id: str | None = None,
    ) -> dict:
        await self.access.ensure_project_access(user_id, project_id, action="write")
        sprint_id = str(body.get("sprintId") or body.get("sprint_id") or "")
        requirement_id = str(body.get("requirementId") or body.get("requirement_id") or "")
        requirement = None
        if kind in {"ui", "requirement_analysis", "code_risk_analysis"}:
            if not requirement_id:
                raise ErrBadRequest()
            requirement = await self.repository.get_requirement(requirement_id)
            if requirement is None:
                raise ErrNotFound()
            sprint = await self.repository.get_sprint(requirement.sprint_id)
            if sprint is None or sprint.project_id != project_id:
                raise ErrNotFound()
            sprint_id = requirement.sprint_id
        if kind == "test_report":
            if not sprint_id:
                raise ErrBadRequest()
            sprint = await self.repository.get_sprint(sprint_id)
            if sprint is None or sprint.project_id != project_id:
                raise ErrNotFound()
            existing = await self.repository.get_active_task_by_project_sprint_type(
                project_id, sprint_id, task_type_for(kind)
            )
            if existing is not None:
                raise ErrBadRequest()
        if sprint_id:
            await self.access.ensure_sprint_access(user_id, sprint_id, action="write")
        if requirement_id:
            await self.access.ensure_requirement_access(user_id, requirement_id, action="write")
        await self.access.validate_task_scope(
            SimpleNamespace(
                project_id=project_id, sprint_id=sprint_id, requirement_id=requirement_id
            )
        )
        task = AiGenerateTask(
            task_id=task_id or self.id_factory(),
            task_type=task_type_for(kind),
            name=str(
                body.get("name")
                or (
                    f"{requirement.name} analysis"
                    if kind == "requirement_analysis" and requirement is not None
                    else (
                        f"{requirement.name} 代码风险分析"
                        if kind == "code_risk_analysis" and requirement is not None
                        else (
                            "test-report-generate-task"
                            if kind == "test_report"
                            else f"{kind}-case-generate-task"
                        )
                    )
                )
            ),
            project_id=project_id,
            sprint_id=sprint_id,
            requirement_id=requirement_id,
            creator_user_id=user_id,
            source_type=str(
                "source_archive"
                if kind == "ui"
                else requirement.document_type
                if kind in {"requirement_analysis", "code_risk_analysis"}
                and requirement is not None
                else (
                    "daily_metrics"
                    if kind == "test_report"
                    else body.get("sourceType") or body.get("source_type") or "manual"
                )
            ),
            source_content=str(
                ""
                if kind == "ui"
                else requirement.document_content
                if kind in {"requirement_analysis", "code_risk_analysis"}
                and requirement is not None
                else body.get("sourceContent") or body.get("source_content") or ""
            ),
            instruction=str(body.get("instruction") or ""),
        )
        self.repository.add(task)
        await self.repository.commit()
        await self.repository.refresh(task)
        return dump_task(task)

    async def update(
        self,
        kind: str,
        task_id: str,
        body: dict[str, Any],
        user_id: str,
        *,
        current_read: bool = False,
    ) -> dict:
        task = await self.access.owned_task(
            user_id, task_id, kind, action="write", current_read=current_read
        )
        if kind == "ui":
            requirement_key = "requirementId" if "requirementId" in body else "requirement_id"
            if requirement_key in body:
                requirement_id = str(body.get(requirement_key) or "")
                if not requirement_id:
                    raise ErrBadRequest()
                requirement = await self.repository.get_requirement(requirement_id)
                if requirement is None:
                    raise ErrNotFound()
                sprint = await self.repository.get_sprint(requirement.sprint_id)
                if sprint is None or sprint.project_id != task.project_id:
                    raise ErrNotFound()
                await self.access.ensure_requirement_access(user_id, requirement_id, action="write")
                task.requirement_id = requirement_id
                task.sprint_id = requirement.sprint_id
            field_map = {"name": "name", "instruction": "instruction"}
            task.source_type = "source_archive"
            task.source_content = ""
        else:
            field_map = {
                "name": "name",
                "sourceType": "source_type",
                "source_type": "source_type",
                "sourceContent": "source_content",
                "source_content": "source_content",
                "instruction": "instruction",
            }
        for key, attr in field_map.items():
            if key in body:
                setattr(task, attr, body[key])
        await self.repository.commit()
        await self.repository.refresh(task)
        archive = (
            await self.source_archive_repository.get_source_archive(task.task_id)
            if kind == "ui"
            else None
        )
        return dump_task(task, archive)

    async def delete(self, kind: str, task_id: str, user_id: str) -> dict:
        task = await self.access.owned_task(user_id, task_id, kind, action="write")
        await self.deletion.delete(self.repository.session, task)
        await self.repository.commit()
        return {}

    async def delete_run(self, kind: str, run_id: str, user_id: str) -> dict:
        run = await self.access.owned_run(user_id, run_id, kind, action="write")
        if run.status in RUN_ACTIVE_STATUSES:
            raise ErrAiGenerateTaskRunRunning()
        await self.deletion.delete(self.repository.session, run)
        await self.repository.commit()
        return {}
