from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import (
    get_current_user_id,
    get_generation_queries,
    get_generation_stages,
)
from testing_agent.core.errors import success_payload
from testing_agent.schemas.ai_generate_task import AiGenerateTaskRunRequest
from testing_agent.services.ai_stage_workflow import GenerationStageWorkflow
from testing_agent.services.ai_task_queries import GenerationQueries


async def get_function_case_generate_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(await service.get("function", task_id, user_id))


async def get_function_case_generate_task_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: GenerationQueries = Depends(get_generation_queries),
):
    return success_payload(await service.get_run("function", run_id, user_id))


async def generate_function_case_relation_analysis(
    run_id: str,
    body: AiGenerateTaskRunRequest | None = None,
    user_id: str = Depends(get_current_user_id),
    service: GenerationStageWorkflow = Depends(get_generation_stages),
):
    payload = body.model_dump(by_alias=True, exclude_none=True) if body else None
    return success_payload(await service.generate_relation_analysis(run_id, payload, user_id))
