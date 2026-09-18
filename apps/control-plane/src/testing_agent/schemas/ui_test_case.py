from __future__ import annotations

# ruff: noqa: F401
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


def parse_steps_json(value: Any) -> list[Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("stepsJson 必须是合法的 JSON 数组") from exc
    if not isinstance(value, list):
        raise ValueError("stepsJson 必须是数组")
    return value


class UiCaseRequest(BaseModel):
    name: str
    enabled: bool = True
    order_no: int = Field(default=0)
    steps_json: list[Any] = Field()
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    @field_validator("steps_json", mode="before")
    @classmethod
    def validate_steps_json(cls, value: Any) -> list[Any]:
        return parse_steps_json(value)


class UiCaseUpdateRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    order_no: int | None = Field(default=None)
    steps_json: list[Any] | None = Field(default=None)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    @field_validator("steps_json", mode="before")
    @classmethod
    def validate_steps_json(cls, value: Any) -> list[Any] | None:
        return None if value is None else parse_steps_json(value)


class UiCaseResponse(UiCaseRequest):
    case_id: str = Field()
    suite_id: str = Field()
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)


class UiCaseImportResponse(BaseModel):
    imported: int
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
