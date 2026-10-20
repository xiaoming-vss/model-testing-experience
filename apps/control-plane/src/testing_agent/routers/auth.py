from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.auth import (
    auth_config,
    change_password,
    get_profile,
    login,
    logout,
    register,
    update_profile,
)
from testing_agent.schemas.auth import AuthConfigResponse, LoginResponse, UserResponse
from testing_agent.schemas.common import ApiResponse, EmptyData

router = APIRouter()

router.post("/register", response_model=ApiResponse[UserResponse])(register)
router.post("/login", response_model=ApiResponse[LoginResponse])(login)
router.post("/logout", response_model=ApiResponse[EmptyData])(logout)
router.get("/user", response_model=ApiResponse[UserResponse])(get_profile)
router.put("/user", response_model=ApiResponse[UserResponse])(update_profile)
router.put("/user/password", response_model=ApiResponse[EmptyData])(change_password)

router.get("/auth/config", response_model=ApiResponse[AuthConfigResponse])(auth_config)
