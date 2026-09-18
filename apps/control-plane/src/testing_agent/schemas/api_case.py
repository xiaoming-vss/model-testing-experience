from __future__ import annotations

# ruff: noqa: F401
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class ApiCaseRequest(BaseModel):
    name: str
    description: str = ""
    enabled: bool = True
    order_no: int = Field(default=0)
    method: str
    url_template: str = Field()
    headers_json: str = Field(default="")
    query_json: str = Field(default="")
    body_type: str = Field(default="json")
    body_json: str = Field(default="")
    body_text: str = Field(default="")
    timeout_ms: int = Field(default=5000)
    continue_on_failure: bool = Field(default=False)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    @field_validator("headers_json", "query_json", "body_json", mode="before")
    @classmethod
    def dump_json_like_value(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)


class ApiCaseUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    order_no: int | None = Field(default=None)
    method: str | None = None
    url_template: str | None = Field(default=None)
    headers_json: str | None = Field(default=None)
    query_json: str | None = Field(default=None)
    body_type: str | None = Field(default=None)
    body_json: str | None = Field(default=None)
    body_text: str | None = Field(default=None)
    timeout_ms: int | None = Field(default=None)
    continue_on_failure: bool | None = Field(default=None)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    @field_validator("headers_json", "query_json", "body_json", mode="before")
    @classmethod
    def dump_json_like_value(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)


class ApiCaseResponse(ApiCaseRequest):
    case_id: str = Field()
    collection_id: str = Field()
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)
