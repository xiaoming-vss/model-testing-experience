"""Dependencies required by independent generation checkpoint commands."""

from collections.abc import Callable
from typing import Any, Protocol

from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.standalone_run import StandaloneRun


class StandaloneStageContext(Protocol):
    repository: AiGenerateTaskRepository
    new_id: Callable[[], str]

    async def stage_connection(
        self, run: Any, body: Any, user_id: Any, previous_id: Any
    ) -> str: ...

    async def prepare_revision_attachments(
        self, user_id: str, run: StandaloneRun, body: dict[str, Any]
    ) -> tuple[dict[str, str], ...]: ...
