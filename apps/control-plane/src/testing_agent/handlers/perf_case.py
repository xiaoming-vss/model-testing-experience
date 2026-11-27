from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import get_current_user_id, get_perf_case_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.case_lifecycle import CaseInvalidationRequest
from testing_agent.schemas.perf_case import PerfCaseCreate, PerfCaseUpdate
from testing_agent.services.perf_case import PerfCaseService


async def create_perf_case(
    project_id: str,
    body: PerfCaseCreate,
    user_id: str = Depends(get_current_user_id),
    service: PerfCaseService = Depends(get_perf_case_service),
):
    return success_payload(await service.create(user_id, project_id, body))


async def batch_invalidate_perf_cases(
    project_id: str,
    body: CaseInvalidationRequest,
    user_id: str = Depends(get_current_user_id),
    service: PerfCaseService = Depends(get_perf_case_service),
):
    return success_payload(
        await service.batch_set_invalidated(user_id, project_id, body.case_ids, body.invalidated)
    )


async def update_perf_case(
    case_id: str,
    body: PerfCaseUpdate,
    user_id: str = Depends(get_current_user_id),
    service: PerfCaseService = Depends(get_perf_case_service),
):
    return success_payload(await service.update(user_id, case_id, body))


async def delete_perf_case(
    case_id: str,
    user_id: str = Depends(get_current_user_id),
    service: PerfCaseService = Depends(get_perf_case_service),
):
    return success_payload(await service.delete(user_id, case_id))
