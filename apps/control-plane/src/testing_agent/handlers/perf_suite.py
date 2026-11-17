from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import get_current_user_id, get_perf_suite_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.perf_suite import (
    PerfSuiteCaseOrderUpdate,
    PerfSuiteCreate,
    PerfSuiteUpdate,
)
from testing_agent.services.perf_suite import PerfSuiteService


async def create_perf_suite(
    project_id: str,
    body: PerfSuiteCreate,
    user_id: str = Depends(get_current_user_id),
    service: PerfSuiteService = Depends(get_perf_suite_service),
):
    return success_payload(await service.create(user_id, project_id, body))


async def list_perf_suites(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: PerfSuiteService = Depends(get_perf_suite_service),
):
    return success_payload(await service.list(user_id, project_id))


async def get_perf_suite(
    suite_id: str,
    user_id: str = Depends(get_current_user_id),
    service: PerfSuiteService = Depends(get_perf_suite_service),
):
    return success_payload(await service.get(user_id, suite_id))


async def update_perf_suite(
    suite_id: str,
    body: PerfSuiteUpdate,
    user_id: str = Depends(get_current_user_id),
    service: PerfSuiteService = Depends(get_perf_suite_service),
):
    return success_payload(await service.update(user_id, suite_id, body))


async def reorder_perf_suite_cases(
    suite_id: str,
    body: PerfSuiteCaseOrderUpdate,
    user_id: str = Depends(get_current_user_id),
    service: PerfSuiteService = Depends(get_perf_suite_service),
):
    return success_payload(await service.reorder(user_id, suite_id, body))


async def delete_perf_suite(
    suite_id: str,
    user_id: str = Depends(get_current_user_id),
    service: PerfSuiteService = Depends(get_perf_suite_service),
):
    return success_payload(await service.delete(user_id, suite_id))
