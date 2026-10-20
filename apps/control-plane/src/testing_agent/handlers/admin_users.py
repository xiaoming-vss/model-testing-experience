from __future__ import annotations

from fastapi import Depends, Query

from testing_agent.api.deps import get_user_admin_service, require_super_admin
from testing_agent.core.errors import success_payload
from testing_agent.schemas.admin_user import (
    DisableUserRequest,
    ResetPasswordRequest,
    UpdateUserEmailRequest,
)
from testing_agent.services.user_admin import UserAdminService


async def list_users(
    actor_id: str = Depends(require_super_admin),
    search: str = Query(default="", max_length=100),
    status: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    service: UserAdminService = Depends(get_user_admin_service),
):
    return success_payload(
        await service.list(actor_id, search=search, status=status, page=page, page_size=page_size)
    )


async def disable_user(
    user_id: str,
    body: DisableUserRequest,
    actor_id: str = Depends(require_super_admin),
    service: UserAdminService = Depends(get_user_admin_service),
):
    return success_payload(await service.disable(actor_id, user_id, body.reason))


async def enable_user(
    user_id: str,
    actor_id: str = Depends(require_super_admin),
    service: UserAdminService = Depends(get_user_admin_service),
):
    return success_payload(await service.enable(actor_id, user_id))


async def reset_user_password(
    user_id: str,
    body: ResetPasswordRequest,
    actor_id: str = Depends(require_super_admin),
    service: UserAdminService = Depends(get_user_admin_service),
):
    return success_payload(await service.reset_password(actor_id, user_id, body.new_password))


async def revoke_user_sessions(
    user_id: str,
    actor_id: str = Depends(require_super_admin),
    service: UserAdminService = Depends(get_user_admin_service),
):
    return success_payload(await service.revoke_sessions(actor_id, user_id))


async def update_user_email(
    user_id: str,
    body: UpdateUserEmailRequest,
    actor_id: str = Depends(require_super_admin),
    service: UserAdminService = Depends(get_user_admin_service),
):
    return success_payload(await service.update_email(actor_id, user_id, body.email))


async def delete_user(
    user_id: str,
    actor_id: str = Depends(require_super_admin),
    service: UserAdminService = Depends(get_user_admin_service),
):
    return success_payload(await service.delete(actor_id, user_id))
