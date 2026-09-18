from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.ui_test_case_run import (
    debug_run_ui_case,
    get_ui_case_run,
    get_ui_suite_run,
    get_ui_suite_run_report,
    list_ui_suite_runs,
    run_ui_suite,
)
from testing_agent.schemas.common import ApiResponse, ListResponse
from testing_agent.schemas.ui_run import (
    UiCaseRunResponse,
    UiSuiteRunReportResponse,
    UiSuiteRunResponse,
)

router = APIRouter()

router.post(
    "/ui-test-cases/{case_id}/debug-run",
    response_model=ApiResponse[UiCaseRunResponse],
)(debug_run_ui_case)
router.get("/ui-test-case-runs/{run_id}", response_model=ApiResponse[UiCaseRunResponse])(
    get_ui_case_run
)
router.post(
    "/ui-test-suites/{suite_id}/run",
    response_model=ApiResponse[UiSuiteRunResponse],
)(run_ui_suite)
router.get(
    "/ui-test-suites/{suite_id}/runs",
    response_model=ApiResponse[ListResponse[UiSuiteRunResponse]],
)(list_ui_suite_runs)
router.get(
    "/ui-test-suite-runs/{suite_run_id}",
    response_model=ApiResponse[UiSuiteRunResponse],
)(get_ui_suite_run)
router.get(
    "/ui-test-suite-runs/{suite_run_id}/report",
    response_model=ApiResponse[UiSuiteRunReportResponse],
)(get_ui_suite_run_report)
