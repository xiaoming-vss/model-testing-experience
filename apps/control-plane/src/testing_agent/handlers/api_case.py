from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import get_api_case_service, get_current_user_id
from testing_agent.core.errors import success_payload
from testing_agent.schemas.api_case import ApiCaseRequest, ApiCaseUpdateRequest
from testing_agent.schemas.api_run import RunApiCaseRequest
from testing_agent.services.api_case import ApiCaseService


async def create_api_case(
    collection_id: str,
    body: ApiCaseRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiCaseService = Depends(get_api_case_service),
):
    return success_payload(await service.create(user_id, collection_id, body))


async def list_api_cases(
    collection_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiCaseService = Depends(get_api_case_service),
):
    return success_payload(await service.list_by_collection(user_id, collection_id))


async def get_api_case(
    case_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiCaseService = Depends(get_api_case_service),
):
    return success_payload(await service.get(user_id, case_id))


async def update_api_case(
    case_id: str,
    body: ApiCaseUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiCaseService = Depends(get_api_case_service),
):
    return success_payload(
        await service.update(user_id, case_id, body.model_dump(by_alias=True, exclude_none=True))
    )


async def delete_api_case(
    case_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiCaseService = Depends(get_api_case_service),
):
    return success_payload(await service.delete(user_id, case_id))


async def run_api_case(
    case_id: str,
    body: RunApiCaseRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiCaseService = Depends(get_api_case_service),
):
    return success_payload(await service.run(user_id, case_id, body))


async def get_api_case_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiCaseService = Depends(get_api_case_service),
):
    return success_payload(await service.get_run(user_id, run_id))
