from __future__ import annotations

from fastapi import Depends, Query

from testing_agent.api.deps import get_current_user_id, get_perf_suite_run_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.perf_suite_run import PerfSuiteRunCreate
from testing_agent.services.perf_suite_run import PerfSuiteRunService


async def create_perf_suite_run(
    suite_id: str,
    body: PerfSuiteRunCreate,
    user_id: str = Depends(get_current_user_id),
    service: PerfSuiteRunService = Depends(get_perf_suite_run_service),
):
    return success_payload(await service.run(user_id, suite_id, body))


async def list_perf_suite_runs(
    project_id: str,
    suite_id: str = Query(default="", alias="suiteId"),
    status: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    service: PerfSuiteRunService = Depends(get_perf_suite_run_service),
):
    return success_payload(
        await service.list_runs(
            user_id,
            project_id,
            suite_id=suite_id,
            status=status,
            page=page,
            page_size=page_size,
        )
    )


async def get_perf_suite_run(
    suite_run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: PerfSuiteRunService = Depends(get_perf_suite_run_service),
):
    return success_payload(await service.get(user_id, suite_run_id))


async def stop_perf_suite_run(
    suite_run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: PerfSuiteRunService = Depends(get_perf_suite_run_service),
):
    return success_payload(await service.stop(user_id, suite_run_id))
