from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import get_api_environment_var_service, get_current_user_id
from testing_agent.core.errors import success_payload
from testing_agent.schemas.api_environment_var import (
    ApiEnvironmentVarRequest,
    ApiEnvironmentVarUpdateRequest,
)
from testing_agent.services.api_environment_var import ApiEnvironmentVarService


async def create_api_environment_var(
    environment_id: str,
    body: ApiEnvironmentVarRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiEnvironmentVarService = Depends(get_api_environment_var_service),
):
    return success_payload(await service.create(user_id, environment_id, body))


async def list_api_environment_vars(
    environment_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiEnvironmentVarService = Depends(get_api_environment_var_service),
):
    return success_payload(await service.list(user_id, environment_id))


async def get_api_environment_var(
    env_var_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiEnvironmentVarService = Depends(get_api_environment_var_service),
):
    return success_payload(await service.get(user_id, env_var_id))


async def update_api_environment_var(
    env_var_id: str,
    body: ApiEnvironmentVarUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    service: ApiEnvironmentVarService = Depends(get_api_environment_var_service),
):
    return success_payload(
        await service.update(user_id, env_var_id, body.model_dump(by_alias=True, exclude_none=True))
    )


async def delete_api_environment_var(
    env_var_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ApiEnvironmentVarService = Depends(get_api_environment_var_service),
):
    return success_payload(await service.delete(user_id, env_var_id))
