from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.code_risk_analysis_task import (
    create_code_risk_analysis_task,
    delete_code_risk_analysis_run,
    delete_code_risk_analysis_task,
    get_code_risk_analysis_run,
    get_code_risk_analysis_task,
    list_code_risk_analysis_task_runs,
    list_code_risk_analysis_tasks,
    run_code_risk_analysis_task,
)
from testing_agent.schemas.ai_generate_task import (
    AiGenerateTaskResponse,
    CodeRiskAnalysisRunResponse,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse

router = APIRouter()

router.post(
    "/projects/{project_id}/code-risk-analysis-tasks",
    response_model=ApiResponse[AiGenerateTaskResponse],
)(create_code_risk_analysis_task)
router.get(
    "/projects/{project_id}/code-risk-analysis-tasks",
    response_model=ApiResponse[ListResponse[AiGenerateTaskResponse]],
)(list_code_risk_analysis_tasks)
router.get(
    "/code-risk-analysis-tasks/{task_id}",
    response_model=ApiResponse[AiGenerateTaskResponse],
)(get_code_risk_analysis_task)
router.post(
    "/code-risk-analysis-tasks/{task_id}/run",
    response_model=ApiResponse[CodeRiskAnalysisRunResponse],
)(run_code_risk_analysis_task)
router.get(
    "/code-risk-analysis-tasks/{task_id}/runs",
    response_model=ApiResponse[ListResponse[CodeRiskAnalysisRunResponse]],
)(list_code_risk_analysis_task_runs)
router.get(
    "/code-risk-analysis-runs/{run_id}",
    response_model=ApiResponse[CodeRiskAnalysisRunResponse],
)(get_code_risk_analysis_run)

router.delete(
    "/code-risk-analysis-runs/{run_id}",
    response_model=ApiResponse[EmptyData],
)(delete_code_risk_analysis_run)

router.delete("/code-risk-analysis-tasks/{task_id}", response_model=ApiResponse[EmptyData])(
    delete_code_risk_analysis_task
)
