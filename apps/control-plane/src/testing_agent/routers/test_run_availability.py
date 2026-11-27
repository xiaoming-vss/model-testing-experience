"""Approximate API/UI worker availability; dispatch remains authoritative."""

from fastapi import APIRouter

from testing_agent.handlers.test_run_availability import get_test_run_availability
from testing_agent.schemas.common import ApiResponse
from testing_agent.schemas.test_run import AvailabilityResponse

router = APIRouter()

router.get("/test-run-availability", response_model=ApiResponse[AvailabilityResponse])(
    get_test_run_availability
)
