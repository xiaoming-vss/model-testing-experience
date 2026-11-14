from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from testing_agent.core.errors import (
    ErrBadRequest,
    ErrNotFound,
)
from testing_agent.domain.ai_tasks import (
    task_type_for,
)
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.project_access import ProjectAction, require_project_access
from testing_agent.services.standalone_run import StandaloneRun


class RequirementScope(Protocol):
    @property
    def sprint_id(self) -> str: ...


class SprintScope(Protocol):
    @property
    def project_id(self) -> str: ...


class OrderScope(Protocol):
    @property
    def project_id(self) -> str: ...

    @property
    def sprint_id(self) -> str: ...


class TaskScope(RequirementScope, SprintScope, Protocol):
    @property
    def requirement_id(self) -> str: ...


ScopeResources = tuple[
    Mapping[str, RequirementScope],
    Mapping[str, SprintScope],
    Mapping[str, OrderScope],
]


class GenerationAccess:
    """Current resource scope, project actions and parent-before-child locking."""

    def __init__(self, repository: AiGenerateTaskRepository) -> None:
        self.repository = repository

    async def ensure_project_access(
        self, user_id: str, project_id: str, *, action: ProjectAction = "read"
    ) -> None:
        getter = self.repository.get_project
        if action != "read":
            getter = getattr(self.repository, "get_project_for_update", getter)
        project = await getter(project_id)
        if project is None:
            raise ErrNotFound()
        await require_project_access(self.repository.session, user_id, project, action)

    async def ensure_sprint_access(
        self, user_id: str, sprint_id: str, *, action: ProjectAction = "read"
    ) -> None:
        getter = self.repository.get_sprint
        if action != "read":
            getter = getattr(self.repository, "get_sprint_for_update", getter)
        sprint = await getter(sprint_id)
        if sprint is None:
            raise ErrNotFound()
        await self.ensure_project_access(user_id, sprint.project_id, action=action)

    async def ensure_requirement_access(
        self, user_id: str, requirement_id: str, *, action: ProjectAction = "read"
    ) -> None:
        getter = self.repository.get_requirement
        if action != "read":
            getter = getattr(self.repository, "get_requirement_for_update", getter)
        requirement = await getter(requirement_id)
        if requirement is None:
            raise ErrNotFound()
        await self.ensure_sprint_access(user_id, requirement.sprint_id, action=action)

    async def ensure_collection_access(
        self, user_id: str, collection_id: str, *, action: ProjectAction = "read"
    ) -> None:
        collection = await self.repository.get_collection(collection_id)
        if collection is None:
            raise ErrNotFound()
        await self.ensure_requirement_access(user_id, collection.requirement_id, action=action)

    async def validate_task_scope(
        self, task: TaskScope, resources: ScopeResources | None = None
    ) -> None:
        """Reject legacy or new references outside the task's project and sprint."""
        scope_loader = getattr(self.repository, "task_scope_resources", None)
        if resources is None and scope_loader is not None:
            resources = await scope_loader([task])
        sprint_id = getattr(task, "sprint_id", "") or ""
        requirement_id = getattr(task, "requirement_id", "") or ""
        if sprint_id:
            sprint = (
                resources[1].get(sprint_id)
                if resources is not None
                else await self.repository.get_sprint(sprint_id)
            )
            if sprint is None or sprint.project_id != task.project_id:
                raise ErrNotFound()
        if requirement_id:
            requirement = (
                resources[0].get(requirement_id)
                if resources is not None
                else await self.repository.get_requirement(requirement_id)
            )
            if requirement is None:
                raise ErrNotFound()
            sprint = (
                resources[1].get(requirement.sprint_id)
                if resources is not None
                else await self.repository.get_sprint(requirement.sprint_id)
            )
            if sprint is None or sprint.project_id != task.project_id:
                raise ErrNotFound()
            if sprint_id and requirement.sprint_id != sprint_id:
                raise ErrBadRequest()
        order_id = getattr(task, "order_id", "") or ""
        if order_id:
            # Older callers and test doubles may still pass a two-item scope tuple;
            # fall back to the single-row lookup only in that case.
            orders = resources[2] if resources is not None and len(resources) > 2 else None
            order = (
                orders.get(order_id)
                if orders is not None
                else await self.repository.get_test_order(order_id)
            )
            if order is None or order.project_id != task.project_id or order.sprint_id != sprint_id:
                raise ErrNotFound()

    async def owned_task(
        self,
        user_id: str,
        task_id: str,
        kind: str | None = None,
        *,
        action: ProjectAction = "read",
        current_read: bool = False,
    ) -> AiGenerateTask:
        getter = self.repository.get_task_for_update if current_read else self.repository.get_task
        task = await getter(task_id)
        if task is None:
            raise ErrNotFound()
        if kind and task.task_type != task_type_for(kind):
            raise ErrNotFound()
        await self.ensure_project_access(user_id, task.project_id, action=action)
        await self.validate_task_scope(task)
        return task

    async def owned_run(
        self, user_id: str, run_id: str, kind: str | None = None, *, action: ProjectAction = "read"
    ) -> StandaloneRun:
        from sqlalchemy import select

        from testing_agent.models.ai_execution import AiExecution
        from testing_agent.repositories.standalone_execution import workflow_task_id
        from testing_agent.services.standalone_execution_view import project_standalone_execution

        session = self.repository.session
        task_id = await workflow_task_id(session, run_id)
        if task_id is None:
            raise ErrNotFound()
        task = await self.owned_task(
            user_id, task_id, kind, action=action, current_read=action != "read"
        )
        if action != "read":
            execution = await session.scalar(
                select(AiExecution)
                .where(AiExecution.execution_id == run_id, AiExecution.task_id == task.task_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if execution is None or execution.workflow_status is None:
                raise ErrNotFound()
        return await project_standalone_execution(session, run_id)
