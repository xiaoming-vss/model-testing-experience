from __future__ import annotations

from fastapi import Depends, Request

from testing_agent.api.deps import (
    get_access_token,
    get_auth_service,
    get_current_user_id,
    get_effective_settings,
)
from testing_agent.core.config import Settings
from testing_agent.core.errors import success_payload
from testing_agent.schemas.auth import (
    AuthConfigResponse,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    UpdateProfileRequest,
)
from testing_agent.services.auth import AuthService


async def register(body: RegisterRequest, service: AuthService = Depends(get_auth_service)):
    return success_payload(await service.register(body))


async def login(
    body: LoginRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    client_ip = request.client.host if request.client else ""
    return success_payload(await service.login(body, client_ip=client_ip))


async def logout(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_access_token),
    service: AuthService = Depends(get_auth_service),
):
    return success_payload(await service.logout(user_id, token))


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


async def change_password(
    body: ChangePasswordRequest,
    user_id: str = Depends(get_current_user_id),
    service: AuthService = Depends(get_auth_service),
):
    return success_payload(await service.change_password(user_id, body))


async def auth_config(settings: Settings = Depends(get_effective_settings)) -> dict:
    return success_payload(
        AuthConfigResponse(
            ldap_enabled=settings.ldap.enabled,
            registration_enabled=not settings.ldap.enabled,
            local_login_admin_only=settings.ldap.enabled,
        ).model_dump(by_alias=True)
    )
