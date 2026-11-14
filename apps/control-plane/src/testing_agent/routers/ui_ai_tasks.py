from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.ui_case_generate_task import (
    create_ui_case_generate_task,
    delete_ui_case_generate_task,
    delete_ui_case_generate_task_run,
    get_ui_case_generate_task,
    get_ui_case_generate_task_run,
    import_ui_case_generate_task_run,
    list_ui_case_generate_task_runs,
    list_ui_case_generate_tasks,
    retry_ui_generation_stage,
    review_ui_case_generate_task_run,
    review_ui_generation_stage,
    revise_ui_generation_stage,
    run_ui_case_generate_task,
    save_ui_generation_stage,
    update_ui_case_generate_task,
    update_ui_case_generate_task_run_result,
)
from testing_agent.schemas.ai_generate_task import (
    AiGenerateRunHistoryResponse,
    AiGenerateTaskListResponse,
    AiGenerateTaskResponse,
    AiGenerateTaskRunResponse,
    UiGenerateTaskImportResponse,
)
from testing_agent.schemas.common import ApiResponse, EmptyData

router = APIRouter()

router.post(
    "/projects/{project_id}/ui-case-generate-tasks",
    response_model=ApiResponse[AiGenerateTaskResponse],
)(create_ui_case_generate_task)
router.get(
    "/projects/{project_id}/ui-case-generate-tasks",
    response_model=ApiResponse[AiGenerateTaskListResponse],
)(list_ui_case_generate_tasks)
router.get("/ui-case-generate-tasks/{task_id}", response_model=ApiResponse[AiGenerateTaskResponse])(
    get_ui_case_generate_task
)
router.patch(
    "/ui-case-generate-tasks/{task_id}", response_model=ApiResponse[AiGenerateTaskResponse]
)(update_ui_case_generate_task)
router.delete("/ui-case-generate-tasks/{task_id}", response_model=ApiResponse[EmptyData])(
    delete_ui_case_generate_task
)
router.post(
    "/ui-case-generate-tasks/{task_id}/run",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(run_ui_case_generate_task)
router.get(
    "/ui-case-generate-tasks/{task_id}/runs",
    response_model=ApiResponse[AiGenerateRunHistoryResponse],
)(list_ui_case_generate_task_runs)
router.get(
    "/ui-case-generate-task-runs/{run_id}",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(get_ui_case_generate_task_run)
router.delete(
    "/ui-case-generate-task-runs/{run_id}",
    response_model=ApiResponse[EmptyData],
)(delete_ui_case_generate_task_run)
router.patch(
    "/ui-case-generate-task-runs/{run_id}/result",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(update_ui_case_generate_task_run_result)
router.post(
    "/ui-case-generate-task-runs/{run_id}/review",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(review_ui_case_generate_task_run)
router.post(
    "/ui-case-generate-task-runs/{run_id}/import",
    response_model=ApiResponse[UiGenerateTaskImportResponse],
)(import_ui_case_generate_task_run)


router.patch(
    "/ui-case-generate-task-runs/{run_id}/stage-output",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(save_ui_generation_stage)
router.post(
    "/ui-case-generate-task-runs/{run_id}/review-stage",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(review_ui_generation_stage)
router.post(
    "/ui-case-generate-task-runs/{run_id}/revise-stage",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(revise_ui_generation_stage)
router.post(
    "/ui-case-generate-task-runs/{run_id}/retry-stage",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(retry_ui_generation_stage)
