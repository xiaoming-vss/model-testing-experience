from __future__ import annotations

from fastapi import Depends, Query

from testing_agent.api.deps import get_current_user_id, get_perf_run_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.perf_run import PerfRunCreate
from testing_agent.services.perf_run import PerfRunService


async def create_perf_run(
    case_id: str,
    body: PerfRunCreate,
    user_id: str = Depends(get_current_user_id),
    service: PerfRunService = Depends(get_perf_run_service),
):
    return success_payload(await service.create(user_id, case_id, body))


async def list_perf_runs(
    project_id: str,
    case_id: str = Query(default="", alias="caseId"),
    status: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    service: PerfRunService = Depends(get_perf_run_service),
):
    return success_payload(
        await service.list_runs(
            user_id,
            project_id,
            case_id=case_id,
            status=status,
            page=page,
            page_size=page_size,
        )
    )


async def get_perf_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: PerfRunService = Depends(get_perf_run_service),
):
    return success_payload(await service.get(user_id, run_id))


async def stop_perf_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: PerfRunService = Depends(get_perf_run_service),
):
    return success_payload(await service.stop(user_id, run_id))
