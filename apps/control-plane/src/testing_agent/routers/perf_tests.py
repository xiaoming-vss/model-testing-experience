from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.perf_case import (
    create_perf_case,
    delete_perf_case,
    get_perf_case,
    list_perf_cases,
    update_perf_case,
)
from testing_agent.handlers.perf_run import (
    create_perf_run,
    get_perf_run,
    list_perf_runs,
    stop_perf_run,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse, StatusData
from testing_agent.schemas.perf_case import PerfCaseResponse, PerfCaseSummaryResponse
from testing_agent.schemas.perf_run import PerfRunResponse, PerfRunSummaryResponse

router = APIRouter()

router.post(
    "/projects/{project_id}/perf-cases",
    response_model=ApiResponse[PerfCaseResponse],
)(create_perf_case)
router.get(
    "/projects/{project_id}/perf-cases",
    response_model=ApiResponse[ListResponse[PerfCaseSummaryResponse]],
)(list_perf_cases)
router.get(
    "/perf-cases/{case_id}",
    response_model=ApiResponse[PerfCaseResponse],
)(get_perf_case)
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
