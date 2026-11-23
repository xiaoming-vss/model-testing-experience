"""Dependencies required by independent generation relation analysis."""

from collections.abc import Callable
from typing import Any, Protocol

from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository


class StandaloneStageContext(Protocol):
    repository: AiGenerateTaskRepository
    new_id: Callable[[], str]

    async def stage_connection(
        self, run: Any, body: Any, user_id: Any, previous_id: Any
    ) -> str: ...
