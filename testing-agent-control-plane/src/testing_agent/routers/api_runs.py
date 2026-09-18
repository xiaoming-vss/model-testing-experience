from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.api_case import get_api_case_run, run_api_case
from testing_agent.handlers.api_collection_run import (
    get_api_collection_run,
    get_api_collection_run_report,
    list_api_collection_runs,
    run_api_collection,
)
from testing_agent.schemas.api_run import (
    ApiCaseRunResponse,
    ApiCollectionRunReportResponse,
    ApiCollectionRunResponse,
)
from testing_agent.schemas.common import ApiResponse, ListResponse

router = APIRouter()

router.post("/api-cases/{case_id}/run", response_model=ApiResponse[ApiCaseRunResponse])(
    run_api_case
)
router.get("/api-case-runs/{run_id}", response_model=ApiResponse[ApiCaseRunResponse])(
    get_api_case_run
)
router.post(
    "/api-collections/{collection_id}/run",
    response_model=ApiResponse[ApiCollectionRunResponse],
)(run_api_collection)
router.get(
    "/api-collections/{collection_id}/runs",
    response_model=ApiResponse[ListResponse[ApiCollectionRunResponse]],
)(list_api_collection_runs)
router.get(
    "/api-collection-runs/{collection_run_id}",
    response_model=ApiResponse[ApiCollectionRunResponse],
)(get_api_collection_run)
router.get(
    "/api-collection-runs/{collection_run_id}/report",
    response_model=ApiResponse[ApiCollectionRunReportResponse],
)(get_api_collection_run_report)
