from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.function_case_generate_task import (
    create_function_case_generate_task,
    delete_function_case_generate_task,
    get_function_case_generate_task,
    get_function_case_generate_task_run,
    import_function_case_generate_task_run,
    list_function_case_generate_task_runs,
    list_function_case_generate_tasks,
    retry_function_case_stage,
    review_function_case_generate_task_run,
    review_function_case_stage,
    revise_function_case_stage,
    run_function_case_generate_task,
    save_function_case_stage_output,
    update_function_case_generate_task,
    update_function_case_generate_task_run_result,
)
from testing_agent.schemas.ai_generate_task import (
    AiGenerateTaskResponse,
    AiGenerateTaskRunResponse,
    FunctionGenerateTaskImportResponse,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse

router = APIRouter()

router.post(
    "/projects/{project_id}/function-case-generate-tasks",
    response_model=ApiResponse[AiGenerateTaskResponse],
)(create_function_case_generate_task)
router.get(
    "/projects/{project_id}/function-case-generate-tasks",
    response_model=ApiResponse[ListResponse[AiGenerateTaskResponse]],
)(list_function_case_generate_tasks)
router.get(
    "/function-case-generate-tasks/{task_id}",
    response_model=ApiResponse[AiGenerateTaskResponse],
)(get_function_case_generate_task)
router.patch(
    "/function-case-generate-tasks/{task_id}",
    response_model=ApiResponse[AiGenerateTaskResponse],
)(update_function_case_generate_task)
router.delete(
    "/function-case-generate-tasks/{task_id}",
    response_model=ApiResponse[EmptyData],
)(delete_function_case_generate_task)
router.post(
    "/function-case-generate-tasks/{task_id}/run",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(run_function_case_generate_task)
router.get(
    "/function-case-generate-tasks/{task_id}/runs",
    response_model=ApiResponse[ListResponse[AiGenerateTaskRunResponse]],
)(list_function_case_generate_task_runs)
router.get(
    "/function-case-generate-task-runs/{run_id}",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(get_function_case_generate_task_run)
router.patch(
    "/function-case-generate-task-runs/{run_id}/stage-output",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(save_function_case_stage_output)
router.post(
    "/function-case-generate-task-runs/{run_id}/stage-review",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(review_function_case_stage)
router.post(
    "/function-case-generate-task-runs/{run_id}/stage-retry",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(retry_function_case_stage)
router.post(
    "/function-case-generate-task-runs/{run_id}/review",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(review_function_case_generate_task_run)
router.patch(
    "/function-case-generate-task-runs/{run_id}/result",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(update_function_case_generate_task_run_result)
router.post(
    "/function-case-generate-task-runs/{run_id}/import",
    response_model=ApiResponse[FunctionGenerateTaskImportResponse],
)(import_function_case_generate_task_run)

router.post(
    "/function-case-generate-task-runs/{run_id}/stage-revise",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(revise_function_case_stage)
