"""Approximate API/UI worker availability for the run toolbar."""

from fastapi import Depends

from testing_agent.api.deps import get_current_user_id, get_test_run_availability_service
from testing_agent.core.errors import success_payload
from testing_agent.services.test_run_availability import TestRunAvailabilityService


async def get_test_run_availability(
    user_id: str = Depends(get_current_user_id),
    service: TestRunAvailabilityService = Depends(get_test_run_availability_service),
):
    del user_id
    return success_payload({"state": await service.state()})
