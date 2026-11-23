from __future__ import annotations

# ruff: noqa: F401
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from testing_agent.schemas.common import StrictRequest

UiScreenshotPolicy = Literal["on_failure", "after_each_step", "never"]


class UiSuiteRequest(StrictRequest):
    name: str
    description: str = ""
    headless: bool | None = None
    slow_mo_ms: int | None = Field(default=None)
    viewport_width: int | None = Field(default=None)
    viewport_height: int | None = Field(default=None)
    default_step_timeout_ms: int | None = Field(default=None)
    screenshot_policy: UiScreenshotPolicy = Field(default="on_failure")
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ProjectUiSuiteRequest(UiSuiteRequest):
    requirement_id: str | None = Field(default=None, min_length=1, max_length=64)


class UiSuiteUpdateRequest(StrictRequest):
    requirement_id: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = None
    description: str | None = None
    headless: bool | None = None
    slow_mo_ms: int | None = Field(default=None)
    viewport_width: int | None = Field(default=None)
    viewport_height: int | None = Field(default=None)
    default_step_timeout_ms: int | None = Field(default=None)
    screenshot_policy: UiScreenshotPolicy | None = Field(default=None)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UiSuiteResponse(UiSuiteRequest):
    suite_id: str = Field()
    project_id: str = Field()
    requirement_id: str | None = Field(default=None)
    effective_import_id: str | None = Field(default=None)
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)
