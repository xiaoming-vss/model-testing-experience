"""Authenticated, short-lived subscriptions to committed test run changes."""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from testing_agent.handlers.test_run import stop_test_run, test_run_events
from testing_agent.schemas.common import ApiResponse, StatusData

router = APIRouter()

router.get("/test-run-events/{kind}/{run_id}", response_class=StreamingResponse)(test_run_events)
router.post("/test-runs/{kind}/{run_id}/stop", response_model=ApiResponse[StatusData])(
    stop_test_run
)
