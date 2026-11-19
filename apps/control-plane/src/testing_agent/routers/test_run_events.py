"""Authenticated, short-lived subscriptions to committed test run changes."""

from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from testing_agent.api.deps import (
    get_api_case_service,
    get_api_collection_run_service,
    get_current_user_id,
    get_session,
    get_ui_test_case_run_service,
)
from testing_agent.core.errors import success_payload
from testing_agent.schemas.common import ApiResponse, StatusData
from testing_agent.services.api_case import ApiCaseService
from testing_agent.services.api_collection_run import ApiCollectionRunService
from testing_agent.services.test_run_stop import stop_run
from testing_agent.services.test_run_stream import stream_run_events
from testing_agent.services.ui_test_case_run import UiTestCaseRunService

router = APIRouter()
RunKind = Literal["api-case", "api-collection", "ui-case", "ui-suite"]


@router.get("/test-run-events/{kind}/{run_id}", response_class=StreamingResponse)
async def test_run_events(
    kind: RunKind,
    run_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    session=Depends(get_session),
    api_cases: ApiCaseService = Depends(get_api_case_service),
    api_collections: ApiCollectionRunService = Depends(get_api_collection_run_service),
    ui_runs: UiTestCaseRunService = Depends(get_ui_test_case_run_service),
):
    return await stream_run_events(
        kind, run_id, request, user_id, session, api_cases, api_collections, ui_runs
    )


@router.post("/test-runs/{kind}/{run_id}/stop", response_model=ApiResponse[StatusData])
async def stop_test_run(
    kind: RunKind,
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    session=Depends(get_session),
    api_cases: ApiCaseService = Depends(get_api_case_service),
    api_collections: ApiCollectionRunService = Depends(get_api_collection_run_service),
    ui_runs: UiTestCaseRunService = Depends(get_ui_test_case_run_service),
):
    return success_payload(
        await stop_run(kind, run_id, user_id, session, api_cases, api_collections, ui_runs)
    )
