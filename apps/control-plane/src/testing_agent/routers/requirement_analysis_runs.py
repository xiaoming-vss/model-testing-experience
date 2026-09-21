from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.requirement_analysis_run import (
    create_requirement_analysis_task,
    delete_requirement_analysis_run,
    delete_requirement_analysis_task,
    get_requirement_analysis_run,
    get_requirement_analysis_task,
    import_requirement_analysis_run_to_requirement,
    list_requirement_analysis_task_runs,
    list_requirement_analysis_tasks,
    retry_requirement_analysis_stage,
    review_requirement_analysis_stage,
    revise_requirement_analysis_stage,
    run_requirement_analysis_task,
    save_requirement_analysis_stage_output,
    update_requirement_analysis_task,
)
from testing_agent.schemas.ai_generate_task import (
    AiGenerateTaskResponse,
    AiGenerateTaskRunResponse,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse
from testing_agent.schemas.requirement import RequirementResponse

router = APIRouter()

router.post(
    "/projects/{project_id}/requirement-analysis-tasks",
    response_model=ApiResponse[AiGenerateTaskResponse],
)(create_requirement_analysis_task)
router.get(
    "/projects/{project_id}/requirement-analysis-tasks",
    response_model=ApiResponse[ListResponse[AiGenerateTaskResponse]],
)(list_requirement_analysis_tasks)
router.get(
    "/requirement-analysis-tasks/{task_id}",
    response_model=ApiResponse[AiGenerateTaskResponse],
)(get_requirement_analysis_task)
router.patch(
    "/requirement-analysis-tasks/{task_id}",
    response_model=ApiResponse[AiGenerateTaskResponse],
)(update_requirement_analysis_task)
router.delete(
    "/requirement-analysis-tasks/{task_id}",
    response_model=ApiResponse[EmptyData],
)(delete_requirement_analysis_task)
router.post(
    "/requirement-analysis-tasks/{task_id}/run",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(run_requirement_analysis_task)
router.get(
    "/requirement-analysis-tasks/{task_id}/runs",
    response_model=ApiResponse[ListResponse[AiGenerateTaskRunResponse]],
)(list_requirement_analysis_task_runs)
router.get(
    "/requirement-analysis-runs/{run_id}",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(get_requirement_analysis_run)
router.delete(
    "/requirement-analysis-runs/{run_id}",
    response_model=ApiResponse[EmptyData],
)(delete_requirement_analysis_run)
router.patch(
    "/requirement-analysis-runs/{run_id}/stage-output",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(save_requirement_analysis_stage_output)
router.post(
    "/requirement-analysis-runs/{run_id}/stage-review",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(review_requirement_analysis_stage)
router.post(
    "/requirement-analysis-runs/{run_id}/stage-revise",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(revise_requirement_analysis_stage)
router.post(
    "/requirement-analysis-runs/{run_id}/import-to-requirement",
    response_model=ApiResponse[RequirementResponse],
)(import_requirement_analysis_run_to_requirement)

router.post(
    "/requirement-analysis-runs/{run_id}/stage-retry",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(retry_requirement_analysis_stage)
