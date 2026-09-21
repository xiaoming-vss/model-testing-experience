"""Authorization seams used by generation workflows, independent of their facade."""

from typing import Protocol

from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.project_access import ProjectAction


class OwnedRun(Protocol):
    async def __call__(
        self, user_id: str, run_id: str, kind: str | None = None, *, action: ProjectAction = "read"
    ) -> AiGenerateTaskRun: ...


class OwnedTask(Protocol):
    async def __call__(
        self, user_id: str, task_id: str, kind: str | None = None, *, action: ProjectAction = "read"
    ) -> AiGenerateTask: ...


class RequireProjectAccess(Protocol):
    async def __call__(
        self, user_id: str, project_id: str, *, action: ProjectAction = "read"
    ) -> None: ...


class RequireCollectionAccess(Protocol):
    async def __call__(
        self, user_id: str, collection_id: str, *, action: ProjectAction = "read"
    ) -> None: ...


class CandidateImportContext(Protocol):
    repository: AiGenerateTaskRepository

    async def owned_run(
        self, user_id: str, run_id: str, kind: str | None = None, *, action: ProjectAction = "read"
    ) -> AiGenerateTaskRun: ...

    async def ensure_requirement_access(
        self, user_id: str, requirement_id: str, *, action: ProjectAction = "read"
    ) -> None: ...
