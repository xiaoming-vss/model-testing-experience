from __future__ import annotations

# ruff: noqa: F401
from datetime import UTC, datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from testing_agent.core.enums import SprintStatus


class CreateSprintRequest(BaseModel):
    name: str
    description: str = ""
    start_time: datetime = Field()
    end_time: datetime = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    @field_validator("start_time", "end_time")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        return require_aware_datetime(value)

    @model_validator(mode="after")
    def validate_schedule(self) -> Self:
        if self.end_time <= self.start_time:
            raise ValueError("endTime must be later than startTime")
        return self


class UpdateSprintRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    start_time: datetime | None = Field(default=None)
    end_time: datetime | None = Field(default=None)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def require_non_null_time(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("sprint schedule times cannot be null")
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return require_aware_datetime(value)


class SprintResponse(BaseModel):
    sprint_id: str = Field()
    project_id: str = Field()
    name: str
    description: str = ""
    status: SprintStatus
    start_time: datetime | str | None = Field(default="")
    end_time: datetime | str | None = Field(default="")
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)


def require_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone offset")
    return value.astimezone(UTC)
