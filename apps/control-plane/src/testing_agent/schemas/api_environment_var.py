from __future__ import annotations

# ruff: noqa: F401
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator
from pydantic.alias_generators import to_camel


class ApiEnvironmentVarRequest(BaseModel):
    var_key: str = Field()
    value: str = ""
    description: str = ""
    is_secret: bool = Field(default=False)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiEnvironmentVarUpdateRequest(BaseModel):
    var_key: str | None = Field(default=None)
    value: str | None = None
    description: str | None = None
    is_secret: bool | None = Field(default=None)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiEnvironmentVarResponse(ApiEnvironmentVarRequest):
    @field_serializer("value")
    def hide_secret(self, value: str) -> str:
        return "********" if self.is_secret else value

    env_var_id: str = Field()
    environment_id: str = Field()
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)
