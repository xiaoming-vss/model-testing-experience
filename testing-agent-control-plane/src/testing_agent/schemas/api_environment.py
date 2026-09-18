from __future__ import annotations

# ruff: noqa: F401
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class ApiEnvironmentRequest(BaseModel):
    name: str
    base_url: str = Field(default="")
    description: str = ""
    is_default: bool = Field(default=False)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiEnvironmentUpdateRequest(BaseModel):
    name: str | None = None
    base_url: str | None = Field(default=None)
    description: str | None = None
    is_default: bool | None = Field(default=None)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiEnvironmentResponse(ApiEnvironmentRequest):
    environment_id: str = Field()
    project_id: str = Field()
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)
