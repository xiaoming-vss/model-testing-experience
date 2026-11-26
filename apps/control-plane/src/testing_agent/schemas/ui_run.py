from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from testing_agent.core.enums import RunStatus
from testing_agent.schemas.common import StrictRequest


class DebugRunUiCaseRequest(StrictRequest):
    environment_id: str = Field()
    live_debug: bool = False
    sprint_id: str | None = Field(default=None, min_length=1, max_length=64)
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
    trace_path: str = ""
    run_id: str = Field()
    case_id: str = Field()
    suite_id: str = Field()
    environment_id: str = Field(default="")
    environment_name: str = Field(default="")
    requirement_id: str | None = Field(default=None)
    requirement_name: str = Field(default="")
    sprint_id: str | None = Field(default=None)
    sprint_name: str = Field(default="")
    project_id: str = Field(default="")
    trigger_user_id: str = Field()
    trigger_type: str = Field()
    status: RunStatus
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
    used_variables: list[Any] | None = Field(
        default_factory=list,
        validation_alias=AliasChoices("usedVariables", "used_variables_json"),
        serialization_alias="usedVariables",
    )
    variable_writes: list[Any] | None = Field(
        default_factory=list,
        validation_alias=AliasChoices("variableWrites", "variable_writes_json"),
        serialization_alias="variableWrites",
    )
    error_message: str = Field()
    duration_ms: int = Field()
    started_at: datetime | str | None = Field(default="")
    finished_at: datetime | str | None = Field(default="")
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)


class UiSuiteRunResponse(BaseModel):
    trace_path: str = ""
    suite_run_id: str = Field()
    suite_id: str = Field()
    environment_id: str = Field(default="")
    environment_name: str = Field(default="")
    requirement_id: str | None = Field(default=None)
    requirement_name: str = Field(default="")
    sprint_id: str | None = Field(default=None)
    sprint_name: str = Field(default="")
    project_id: str = Field()
    trigger_user_id: str = Field()
    trigger_type: str = Field()
    status: RunStatus
    total_count: int = Field()
    success_count: int = Field()
    failed_count: int = Field()
    error_count: int = Field()
    skipped_count: int = Field()
    used_variables: list[Any] | None = Field(
        default_factory=list,
        validation_alias=AliasChoices("usedVariables", "used_variables_json"),
        serialization_alias="usedVariables",
    )
    variable_writes: list[Any] | None = Field(
        default_factory=list,
        validation_alias=AliasChoices("variableWrites", "variable_writes_json"),
        serialization_alias="variableWrites",
    )
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
    status: RunStatus
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
