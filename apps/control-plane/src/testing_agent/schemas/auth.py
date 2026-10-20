from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class RegisterRequest(BaseModel):
    name: str
    password: str
    email: str
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LoginRequest(BaseModel):
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


class UpdateProfileRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    name: str | None = None
    email: str | None = None


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    old_password: str
    new_password: str


class AuthConfigResponse(BaseModel):
    ldap_enabled: bool
    registration_enabled: bool
    local_login_admin_only: bool
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
