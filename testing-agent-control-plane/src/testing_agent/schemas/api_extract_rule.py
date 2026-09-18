from __future__ import annotations

# ruff: noqa: F401
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class ApiExtractRuleRequest(BaseModel):
    name: str
    enabled: bool = True
    order_no: int = Field(default=0)
    source: str
    source_expr: str = Field(default="")
    var_key: str = Field()
    default_value: str = Field(default="")
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiExtractRuleUpdateRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    order_no: int | None = Field(default=None)
    source: str | None = None
    source_expr: str | None = Field(default=None)
    var_key: str | None = Field(default=None)
    default_value: str | None = Field(default=None)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiExtractRuleResponse(ApiExtractRuleRequest):
    extract_rule_id: str = Field()
    case_id: str = Field()
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)
