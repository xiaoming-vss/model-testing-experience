from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from testing_agent.schemas.common import StrictRequest


class RegisterRequest(StrictRequest):
    name: str
    password: str
    email: str
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LoginRequest(StrictRequest):
    name: str
    auth_method: Literal["local", "ldap"] = "local"
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    password: str


class UserResponse(BaseModel):
    auth_source: Literal["local", "ldap"] = "local"
    user_id: str = Field()
    name: str
    email: str | None = None
    is_super_admin: bool = False
    must_change_password: bool = False

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LoginResponse(BaseModel):
    access_token: str = Field()
    must_change_password: bool = False
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UpdateProfileRequest(StrictRequest):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    name: str | None = None
    email: str | None = None

    @field_validator("name", "email")
    @classmethod
    def reject_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("字段不能为 null；省略表示保持原值")
        return value


class ChangePasswordRequest(StrictRequest):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    old_password: str
    new_password: str


class AuthConfigResponse(BaseModel):
    ldap_enabled: bool
    registration_enabled: bool
    local_login_admin_only: bool
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
