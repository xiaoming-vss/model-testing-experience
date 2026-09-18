from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import get_api_environment_service, get_current_user_id
from testing_agent.core.errors import success_payload
from testing_agent.schemas.api_environment import ApiEnvironmentRequest, ApiEnvironmentUpdateRequest
from testing_agent.services.api_environment import ApiEnvironmentService


async def create_api_environment(
    project_id: str,
    body: ApiEnvironmentRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiEnvironmentService = Depends(get_api_environment_service),
):
    return success_payload(await service.create(user_id, project_id, body))


async def list_api_environments(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiEnvironmentService = Depends(get_api_environment_service),
):
    return success_payload(await service.list(user_id, project_id))


async def get_api_environment(
    environment_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiEnvironmentService = Depends(get_api_environment_service),
):
    return success_payload(await service.get(user_id, environment_id))


async def update_api_environment(
    environment_id: str,
    body: ApiEnvironmentUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiEnvironmentService = Depends(get_api_environment_service),
):
    return success_payload(
        await service.update(
            user_id,
            environment_id,
            body.model_dump(by_alias=True, exclude_none=True),
        )
    )


async def delete_api_environment(
    environment_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiEnvironmentService = Depends(get_api_environment_service),
):
    return success_payload(await service.delete(user_id, environment_id))
