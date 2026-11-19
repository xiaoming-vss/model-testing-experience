from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from testing_agent.core.enums import AccountStatus, AuthSource
from testing_agent.schemas.common import StrictRequest


class AdminUserResponse(BaseModel):
    user_id: str
    name: str
    email: str | None = None
    status: AccountStatus
    auth_source: AuthSource = AuthSource.LOCAL
    is_super_admin: bool = False
    must_change_password: bool = False
    disabled_at: datetime | None = None
    disabled_reason: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class DisableUserRequest(StrictRequest):
    reason: str = ""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ResetPasswordRequest(StrictRequest):
    new_password: str
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UpdateUserEmailRequest(StrictRequest):
    email: str
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
