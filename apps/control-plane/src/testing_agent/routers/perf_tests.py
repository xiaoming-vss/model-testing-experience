from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.perf_case import (
    batch_invalidate_perf_cases,
    create_perf_case,
    delete_perf_case,
    update_perf_case,
)
from testing_agent.handlers.perf_run import (
    create_perf_run,
    get_perf_run,
    list_perf_runs,
    stop_perf_run,
)
from testing_agent.handlers.perf_suite import (
    create_perf_suite,
    delete_perf_suite,
    get_perf_suite,
    list_perf_suites,
    update_perf_suite,
)
from testing_agent.handlers.perf_suite_run import (
    create_perf_suite_run,
    get_perf_suite_run,
    list_perf_suite_runs,
    stop_perf_suite_run,
)
from testing_agent.schemas.case_lifecycle import CaseInvalidationResponse
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse, StatusData
from testing_agent.schemas.perf_case import PerfCaseResponse
from testing_agent.schemas.perf_run import PerfRunResponse, PerfRunSummaryResponse
from testing_agent.schemas.perf_suite import PerfSuiteResponse, PerfSuiteSummaryResponse
from testing_agent.schemas.perf_suite_run import (
    PerfSuiteRunResponse,
    PerfSuiteRunSummaryResponse,
)

router = APIRouter()

router.post(
    "/projects/{project_id}/perf-cases",
    response_model=ApiResponse[PerfCaseResponse],
)(create_perf_case)
router.post(
    "/projects/{project_id}/perf-cases/batch-invalidation",
    response_model=ApiResponse[CaseInvalidationResponse],
)(batch_invalidate_perf_cases)
router.patch(
    "/perf-cases/{case_id}",
    response_model=ApiResponse[PerfCaseResponse],
)(update_perf_case)
router.delete(
    "/perf-cases/{case_id}",
    response_model=ApiResponse[EmptyData],
)(delete_perf_case)
router.post(
    "/perf-cases/{case_id}/runs",
    response_model=ApiResponse[PerfRunResponse],
)(create_perf_run)
router.get(
    "/projects/{project_id}/perf-runs",
    response_model=ApiResponse[ListResponse[PerfRunSummaryResponse]],
)(list_perf_runs)
router.get(
    "/perf-runs/{run_id}",
    response_model=ApiResponse[PerfRunResponse],
)(get_perf_run)
router.post(
    "/perf-runs/{run_id}/stop",
    response_model=ApiResponse[StatusData],
)(stop_perf_run)

router.post(
    "/projects/{project_id}/perf-suites",
    response_model=ApiResponse[PerfSuiteResponse],
)(create_perf_suite)
router.get(
    "/projects/{project_id}/perf-suites",
    response_model=ApiResponse[ListResponse[PerfSuiteSummaryResponse]],
)(list_perf_suites)
router.get(
    "/perf-suites/{suite_id}",
    response_model=ApiResponse[PerfSuiteResponse],
)(get_perf_suite)
router.patch(
    "/perf-suites/{suite_id}",
    response_model=ApiResponse[PerfSuiteResponse],
)(update_perf_suite)
router.delete(
    "/perf-suites/{suite_id}",
    response_model=ApiResponse[EmptyData],
)(delete_perf_suite)
router.post(
    "/perf-suites/{suite_id}/runs",
    response_model=ApiResponse[PerfSuiteRunResponse],
)(create_perf_suite_run)
router.get(
    "/projects/{project_id}/perf-suite-runs",
    response_model=ApiResponse[ListResponse[PerfSuiteRunSummaryResponse]],
)(list_perf_suite_runs)
router.get(
    "/perf-suite-runs/{suite_run_id}",
    response_model=ApiResponse[PerfSuiteRunResponse],
)(get_perf_suite_run)
router.post(
    "/perf-suite-runs/{suite_run_id}/stop",
    response_model=ApiResponse[StatusData],
)(stop_perf_suite_run)
