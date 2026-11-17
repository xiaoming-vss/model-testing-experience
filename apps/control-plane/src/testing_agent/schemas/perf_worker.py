from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator
from pydantic.alias_generators import to_camel

from testing_agent.schemas.perf_case import PerfDataFile

PerfWorkerRunStatus = Literal["completed", "failed", "stopped", "canceled"]
PerfWorkerOutcome = Literal[
    "passed", "threshold_failed", "inconclusive", "execution_error", "stopped"
]


class PerfClaimResponse(BaseModel):
    task_id: str
    task_type: str
    run_id: str
    status: str
    lease_seconds: int

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PerfSnapshotResponse(BaseModel):
    task_id: str
    run_id: str
    case_name: str
    run_spec: dict[str, JsonValue]
    data_files: list[PerfDataFile] = Field(default_factory=list)
    lease_seconds: int

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PerfStartedRequest(BaseModel):
    worker_id: str
    started_at: str = ""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class PerfHeartbeatRequest(BaseModel):
    worker_id: str

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class PerfHeartbeatResponse(BaseModel):
    stop_requested: bool
    lease_seconds: int

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PerfControlResponse(BaseModel):
    stop_requested: bool

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PerfResultEvent(BaseModel):
    worker_id: str
    run_id: str = ""
    status: PerfWorkerRunStatus
    outcome: PerfWorkerOutcome
    exit_code: int = 0
    started_at: str = ""
    finished_at: str = ""
    duration_ms: int = 0
    k6_version: str = ""
    template_version: str = ""
    script_sha256: str = ""
    summary: dict[str, JsonValue] | None = None
    flags: list[str] = Field(default_factory=list)
    error_message: str = ""
    log_tail: str = ""
    runner: dict[str, JsonValue] | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    @field_validator("log_tail")
    @classmethod
    def _log_tail_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 16 * 1024:
            raise ValueError("logTail 不能超过 16KB")
        return value
