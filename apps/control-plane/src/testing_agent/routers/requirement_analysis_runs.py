from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.requirement_analysis_run import get_requirement_analysis_task
from testing_agent.schemas.ai_generate_task import AiGenerateTaskResponse
from testing_agent.schemas.common import ApiResponse

router = APIRouter()

router.get(
    "/requirement-analysis-tasks/{task_id}",
    response_model=ApiResponse[AiGenerateTaskResponse],
)(get_requirement_analysis_task)
