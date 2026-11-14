from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import get_api_app_service, get_current_user_id
from testing_agent.core.errors import success_payload
from testing_agent.schemas.api_app import ApiAppCreateRequest, ApiAppUpdateRequest
from testing_agent.services.api_app import ApiAppService


async def create_api_app(
    project_id: str,
    body: ApiAppCreateRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiAppService = Depends(get_api_app_service),
):
    return success_payload(await service.create(user_id, project_id, body))


async def list_api_apps(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiAppService = Depends(get_api_app_service),
):
    return success_payload(await service.list(user_id, project_id))


async def get_api_app(
    app_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiAppService = Depends(get_api_app_service),
):
    return success_payload(await service.get(user_id, app_id))


async def update_api_app(
    app_id: str,
    body: ApiAppUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiAppService = Depends(get_api_app_service),
):
    return success_payload(await service.update(user_id, app_id, body))


async def delete_api_app(
    app_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiAppService = Depends(get_api_app_service),
):
    return success_payload(await service.delete(user_id, app_id))
