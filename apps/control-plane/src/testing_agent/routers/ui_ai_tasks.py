from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.ui_case_generate_task import get_ui_case_generate_task
from testing_agent.schemas.ai_generate_task import AiGenerateTaskResponse
from testing_agent.schemas.common import ApiResponse

router = APIRouter()

router.get(
    "/ui-case-generate-tasks/{task_id}",
    response_model=ApiResponse[AiGenerateTaskResponse],
)(get_ui_case_generate_task)
