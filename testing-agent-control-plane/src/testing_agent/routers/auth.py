from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.auth import (
    delete_user,
    get_profile,
    login,
    register,
    update_profile,
)
from testing_agent.schemas.auth import LoginResponse, UserResponse
from testing_agent.schemas.common import ApiResponse, EmptyData

router = APIRouter()

router.post("/register", response_model=ApiResponse[UserResponse])(register)
router.post("/login", response_model=ApiResponse[LoginResponse])(login)
router.get("/user", response_model=ApiResponse[UserResponse])(get_profile)
router.put("/user", response_model=ApiResponse[UserResponse])(update_profile)
router.delete("/user", response_model=ApiResponse[EmptyData])(delete_user)
