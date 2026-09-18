from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import get_auth_service, get_current_user_id
from testing_agent.core.errors import success_payload
from testing_agent.schemas.auth import LoginRequest, RegisterRequest, UpdateProfileRequest
from testing_agent.services.auth import AuthService


async def register(body: RegisterRequest, service: AuthService = Depends(get_auth_service)):
    return success_payload(await service.register(body))


async def login(body: LoginRequest, service: AuthService = Depends(get_auth_service)):
    return success_payload(await service.login(body))


async def get_profile(
    user_id: str = Depends(get_current_user_id),
    service: AuthService = Depends(get_auth_service),
):
    return success_payload(await service.get_profile(user_id))


async def update_profile(
    body: UpdateProfileRequest,
    user_id: str = Depends(get_current_user_id),
    service: AuthService = Depends(get_auth_service),
):
    return success_payload(await service.update_profile(user_id, body))


async def delete_user(
    user_id: str = Depends(get_current_user_id),
    service: AuthService = Depends(get_auth_service),
):
    return success_payload(await service.delete_user(user_id))
