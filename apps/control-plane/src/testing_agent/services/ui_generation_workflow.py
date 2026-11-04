"""Retired UI run URLs; requirement UI stages use the generation chain."""

from typing import Any

from testing_agent.core.errors import ErrNotFound
from testing_agent.services.ai_stage_workflow import GenerationStageWorkflow


class UiGenerationWorkflow(GenerationStageWorkflow):
    async def save_output(self, run_id: str, body: dict[str, Any], user_id: str) -> dict:
        raise ErrNotFound()

    async def review_output(self, run_id: str, body: dict[str, Any], user_id: str) -> dict:
        raise ErrNotFound()

    async def regenerate(self, run_id: str, body: dict[str, Any], user_id: str) -> dict:
        raise ErrNotFound()
