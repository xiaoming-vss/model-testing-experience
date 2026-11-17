from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.function_case_generate_task import (
    generate_function_case_relation_analysis,
    get_function_case_generate_task,
    get_function_case_generate_task_run,
)
from testing_agent.schemas.ai_generate_task import (
    AiGenerateTaskResponse,
    AiGenerateTaskRunResponse,
)
from testing_agent.schemas.common import ApiResponse

router = APIRouter()

router.get(
    "/function-case-generate-tasks/{task_id}",
    response_model=ApiResponse[AiGenerateTaskResponse],
)(get_function_case_generate_task)
router.get(
    "/function-case-generate-task-runs/{run_id}",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(get_function_case_generate_task_run)
router.post(
    "/function-case-generate-task-runs/{run_id}/relation-analysis",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(generate_function_case_relation_analysis)
