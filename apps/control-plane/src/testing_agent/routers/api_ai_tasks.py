from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.api_case_generate_task import get_api_case_generate_task
from testing_agent.schemas.ai_generate_task import AiGenerateTaskResponse
from testing_agent.schemas.common import ApiResponse

router = APIRouter()

router.get(
    "/api-case-generate-tasks/{task_id}",
    response_model=ApiResponse[AiGenerateTaskResponse],
)(get_api_case_generate_task)
