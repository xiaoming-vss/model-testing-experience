from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class RegisterRequest(BaseModel):
    name: str
    password: str
    email: str = ""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LoginRequest(BaseModel):
    name: str
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    password: str


class UserResponse(BaseModel):
    user_id: str = Field()
    name: str
    email: str | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LoginResponse(BaseModel):
    access_token: str = Field()
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UpdateProfileRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    name: str | None = None
    email: str | None = None
