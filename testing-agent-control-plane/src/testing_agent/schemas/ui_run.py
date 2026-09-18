from __future__ import annotations

# ruff: noqa: F401
from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class DebugRunUiCaseRequest(BaseModel):
    headless: bool | None = None
    slow_mo_ms: int | None = Field(default=None)
    viewport_width: int | None = Field(default=None)
    viewport_height: int | None = Field(default=None)
    default_step_timeout_ms: int | None = Field(default=None)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class RunUiSuiteRequest(DebugRunUiCaseRequest):
    pass
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UiCaseRunResponse(BaseModel):
    run_id: str = Field()
    case_id: str = Field()
    suite_id: str = Field()
    requirement_id: str = Field()
    sprint_id: str = Field()
    project_id: str = Field()
    trigger_user_id: str = Field()
    trigger_type: str = Field()
    status: str
    success: bool = False
    snapshot: Any | None = Field(
        default=None,
        validation_alias=AliasChoices("snapshot", "snapshot_json"),
        serialization_alias="snapshot",
    )
    step_results: list[Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("stepResults", "step_results_json"),
        serialization_alias="stepResults",
    )
    error_message: str = Field()
    duration_ms: int = Field()
    started_at: datetime | str | None = Field(default="")
    finished_at: datetime | str | None = Field(default="")
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)


class UiSuiteRunResponse(BaseModel):
    suite_run_id: str = Field()
    suite_id: str = Field()
    requirement_id: str = Field()
    sprint_id: str = Field()
    project_id: str = Field()
    trigger_user_id: str = Field()
    trigger_type: str = Field()
    status: str
    total_count: int = Field()
    success_count: int = Field()
    failed_count: int = Field()
    error_count: int = Field()
    skipped_count: int = Field()
    error_message: str = Field()
    started_at: datetime | str | None = Field(default="")
    finished_at: datetime | str | None = Field(default="")
    duration_ms: int = Field()
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)


class UiSuiteRunReportItem(BaseModel):
    item_id: str = Field()
    case_id: str = Field()
    case_name: str = Field(default="")
    status: str
    order_no: int = Field()
    step_results: list[Any] | None = Field(default_factory=list)
    error_message: str = Field(default="")
    duration_ms: int = Field(default=0)
    started_at: datetime | str | None = Field(default="")
    finished_at: datetime | str | None = Field(default="")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UiSuiteRunReportResponse(UiSuiteRunResponse):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    items: list[UiSuiteRunReportItem]
