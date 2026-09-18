from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from testing_agent.handlers.test_report_generate_task import (
    export_test_report_generate_run_pdf,
    get_test_report_generate_run,
    list_test_report_generate_runs,
    run_test_report_generate_run,
)
from testing_agent.schemas.ai_generate_task import AiGenerateTaskRunResponse
from testing_agent.schemas.common import ApiResponse, ListResponse

router = APIRouter()

router.post(
    "/projects/{project_id}/test-report-generate-runs",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(run_test_report_generate_run)
router.get(
    "/projects/{project_id}/test-report-generate-runs",
    response_model=ApiResponse[ListResponse[AiGenerateTaskRunResponse]],
)(list_test_report_generate_runs)
router.get(
    "/test-report-generate-runs/{run_id}",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(get_test_report_generate_run)
router.get(
    "/test-report-generate-runs/{run_id}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)(export_test_report_generate_run_pdf)
