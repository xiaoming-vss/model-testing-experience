from __future__ import annotations

# ruff: noqa: F401
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class FunctionSuiteRequest(BaseModel):
    name: str
    description: str = ""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class FunctionSuiteUpdateRequest(BaseModel):
    name: str | None = None
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    description: str | None = None


class FunctionSuiteResponse(BaseModel):
    case_count: int = Field(default=0, ge=0)
    suite_id: str = Field()
    requirement_id: str = Field()
    name: str
    description: str = ""
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)
