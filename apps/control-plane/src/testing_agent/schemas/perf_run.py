from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from pydantic.alias_generators import to_camel

from testing_agent.schemas.perf_case import PerfDataFile


class PerfRunCreate(BaseModel):
    environment_id: str = Field(min_length=1, max_length=64)
    monitoring_connection_id: str = Field(min_length=1, max_length=64)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class PerfRunMonitoringSnapshot(BaseModel):
    connection_id: str
    name: str
    remote_write_url: str

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PerfRunSummaryResponse(BaseModel):
    run_id: str
    case_id: str
    project_id: str
    case_version: int
    case_name: str
    environment_id: str
    environment_name: str
    monitoring_connection_id: str
    monitoring_connection_name: str
    trigger_user_id: str
    trigger_type: str
    status: str
    outcome: str | None = ""
    flags: list[str] = Field(default_factory=list)
    error_message: str = ""
    k6_version: str = ""
    template_version: str = ""
    script_sha256: str = ""
    started_at: datetime | str | None = ""
    finished_at: datetime | str | None = ""
    duration_ms: int = 0
    created_at: datetime | str | None = ""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PerfRunResponse(PerfRunSummaryResponse):
    summary: dict[str, JsonValue] | None = None
    log_tail: str = ""
    runner: dict[str, JsonValue] | None = None
    data_files: list[PerfDataFile] = Field(default_factory=list)
    monitoring: PerfRunMonitoringSnapshot | None = None
