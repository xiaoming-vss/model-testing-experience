from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from pydantic.alias_generators import to_camel


class PerfSuiteRunCreate(BaseModel):
    environment_id: str = Field(min_length=1)
    monitoring_connection_id: str = Field(min_length=1)
    sprint_id: str = Field(min_length=1, max_length=64)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class PerfSuiteRunItemResponse(BaseModel):
    item_id: str
    case_id: str
    case_name: str
    order_no: int
    status: str
    outcome: str | None = None
    child_run_id: str = ""
    error_message: str = ""
    started_at: datetime | str | None = ""
    finished_at: datetime | str | None = ""
    duration_ms: int = 0
    summary: dict[str, JsonValue] | None = None
    load: dict[str, JsonValue] | None = None
    log_tail: str = ""
    flags: list[str] = Field(default_factory=list)
    k6_version: str = ""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PerfSuiteRunSummaryResponse(BaseModel):
    suite_run_id: str
    suite_id: str
    project_id: str
    sprint_id: str | None = None
    sprint_name: str = ""
    suite_name: str
    environment_id: str
    environment_name: str
    monitoring_connection_id: str
    monitoring_connection_name: str
    trigger_user_id: str
    trigger_type: str
    status: str
    outcome: str | None = None
    total_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    error_message: str = ""
    started_at: datetime | str | None = ""
    finished_at: datetime | str | None = ""
    duration_ms: int = 0
    created_at: datetime | str | None = ""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PerfSuiteRunResponse(PerfSuiteRunSummaryResponse):
    items: list[PerfSuiteRunItemResponse] = Field(default_factory=list)
