from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import get_current_user_id, get_generation_queries
from testing_agent.core.errors import success_payload
from testing_agent.services.ai_task_queries import GenerationQueries


async def get_api_case_generate_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(await service.get("api", task_id, user_id))
