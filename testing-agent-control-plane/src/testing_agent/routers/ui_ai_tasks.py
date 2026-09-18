from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.ui_case_generate_task import (
    create_ui_case_generate_task,
    delete_ui_case_generate_task,
    get_ui_case_generate_task,
    get_ui_case_generate_task_run,
    import_ui_case_generate_task_run,
    list_ui_case_generate_task_runs,
    list_ui_case_generate_tasks,
    review_ui_case_generate_task_run,
    run_ui_case_generate_task,
    update_ui_case_generate_task,
    update_ui_case_generate_task_run_result,
    upload_ui_case_source_archive,
)
from testing_agent.schemas.ai_generate_task import (
    AiGenerateTaskResponse,
    AiGenerateTaskRunResponse,
    UiGenerateTaskImportResponse,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse

router = APIRouter()

router.post(
    "/projects/{project_id}/ui-case-generate-tasks",
    response_model=ApiResponse[AiGenerateTaskResponse],
)(create_ui_case_generate_task)
router.get(
    "/projects/{project_id}/ui-case-generate-tasks",
    response_model=ApiResponse[ListResponse[AiGenerateTaskResponse]],
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
router.put(
    "/ui-case-generate-tasks/{task_id}/source-archive",
    response_model=ApiResponse[AiGenerateTaskResponse],
)(upload_ui_case_source_archive)
router.post(
    "/ui-case-generate-tasks/{task_id}/run",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(run_ui_case_generate_task)
router.get(
    "/ui-case-generate-tasks/{task_id}/runs",
    response_model=ApiResponse[ListResponse[AiGenerateTaskRunResponse]],
)(list_ui_case_generate_task_runs)
router.get(
    "/ui-case-generate-task-runs/{run_id}",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(get_ui_case_generate_task_run)
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
