from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.api_case_generate_task import (
    create_api_case_generate_task,
    delete_api_case_generate_task,
    get_api_case_generate_task,
    get_api_case_generate_task_run,
    import_api_case_generate_task_run,
    list_api_case_generate_task_runs,
    list_api_case_generate_tasks,
    review_api_case_generate_task_run,
    run_api_case_generate_task,
    update_api_case_generate_task,
    update_api_case_generate_task_run_result,
)
from testing_agent.schemas.ai_generate_task import (
    AiGenerateTaskImportResponse,
    AiGenerateTaskResponse,
    AiGenerateTaskRunResponse,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse

router = APIRouter()

router.post(
    "/projects/{project_id}/api-case-generate-tasks",
    response_model=ApiResponse[AiGenerateTaskResponse],
)(create_api_case_generate_task)
router.get(
    "/projects/{project_id}/api-case-generate-tasks",
    response_model=ApiResponse[ListResponse[AiGenerateTaskResponse]],
)(list_api_case_generate_tasks)
router.get(
    "/api-case-generate-tasks/{task_id}",
    response_model=ApiResponse[AiGenerateTaskResponse],
)(get_api_case_generate_task)
router.patch(
    "/api-case-generate-tasks/{task_id}",
    response_model=ApiResponse[AiGenerateTaskResponse],
)(update_api_case_generate_task)
router.delete(
    "/api-case-generate-tasks/{task_id}",
    response_model=ApiResponse[EmptyData],
)(delete_api_case_generate_task)
router.post(
    "/api-case-generate-tasks/{task_id}/run",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(run_api_case_generate_task)
router.get(
    "/api-case-generate-tasks/{task_id}/runs",
    response_model=ApiResponse[ListResponse[AiGenerateTaskRunResponse]],
)(list_api_case_generate_task_runs)
router.get(
    "/api-case-generate-task-runs/{run_id}",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(get_api_case_generate_task_run)
router.post(
    "/api-case-generate-task-runs/{run_id}/review",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(review_api_case_generate_task_run)
router.patch(
    "/api-case-generate-task-runs/{run_id}/result",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(update_api_case_generate_task_run_result)
router.post(
    "/api-case-generate-task-runs/{run_id}/import",
    response_model=ApiResponse[AiGenerateTaskImportResponse],
)(import_api_case_generate_task_run)
