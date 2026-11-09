from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.repository_profile_task import (
    create_repository_profile_task,
    get_repository_profile_run,
    list_repository_profile_task_runs,
    list_repository_profile_task_versions,
    list_repository_profile_tasks,
    run_repository_profile_task,
)
from testing_agent.schemas.ai_generate_task import (
    AiGenerateRunHistoryResponse,
    AiGenerateTaskResponse,
    RepositoryProfileRunResponse,
    RepositoryProfileVersionResponse,
)
from testing_agent.schemas.common import ApiResponse, ListResponse

router = APIRouter()

router.post(
    "/projects/{project_id}/repository-profile-tasks",
    response_model=ApiResponse[AiGenerateTaskResponse],
)(create_repository_profile_task)
router.get(
    "/projects/{project_id}/repository-profile-tasks",
    response_model=ApiResponse[ListResponse[AiGenerateTaskResponse]],
)(list_repository_profile_tasks)
router.post(
    "/repository-profile-tasks/{task_id}/run",
    response_model=ApiResponse[RepositoryProfileRunResponse],
)(run_repository_profile_task)
router.get(
    "/repository-profile-tasks/{task_id}/runs",
    response_model=ApiResponse[AiGenerateRunHistoryResponse],
)(list_repository_profile_task_runs)
router.get(
    "/repository-profile-tasks/{task_id}/versions",
    response_model=ApiResponse[ListResponse[RepositoryProfileVersionResponse]],
)(list_repository_profile_task_versions)
router.get(
    "/repository-profile-runs/{run_id}",
    response_model=ApiResponse[RepositoryProfileRunResponse],
)(get_repository_profile_run)
