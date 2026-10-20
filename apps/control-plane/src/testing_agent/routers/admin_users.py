from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.admin_users import (
    delete_user,
    disable_user,
    enable_user,
    list_users,
    reset_user_password,
    revoke_user_sessions,
    update_user_email,
)
from testing_agent.schemas.admin_user import AdminUserResponse
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse

router = APIRouter()

router.get("/admin/users", response_model=ApiResponse[ListResponse[AdminUserResponse]])(list_users)
router.post("/admin/users/{user_id}/disable", response_model=ApiResponse[AdminUserResponse])(
    disable_user
)
router.post("/admin/users/{user_id}/enable", response_model=ApiResponse[AdminUserResponse])(
    enable_user
)
router.post("/admin/users/{user_id}/reset-password", response_model=ApiResponse[AdminUserResponse])(
    reset_user_password
)
router.post("/admin/users/{user_id}/revoke-sessions", response_model=ApiResponse[EmptyData])(
    revoke_user_sessions
)
router.put("/admin/users/{user_id}/email", response_model=ApiResponse[AdminUserResponse])(
    update_user_email
)
router.delete("/admin/users/{user_id}", response_model=ApiResponse[EmptyData])(delete_user)
