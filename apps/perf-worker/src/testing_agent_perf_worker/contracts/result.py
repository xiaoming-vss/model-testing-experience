"""Execution result contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from .spec import WireModel


class RunStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"
    CANCELED = "canceled"


class RunOutcome(StrEnum):
    PASSED = "passed"
    THRESHOLD_FAILED = "threshold_failed"
    INCONCLUSIVE = "inconclusive"
    EXECUTION_ERROR = "execution_error"
    STOPPED = "stopped"


class ResultFlag(StrEnum):
    SUMMARY_MISSING = "summary_missing"
    LOG_TRUNCATED = "log_truncated"
    REMOTE_WRITE_ERROR = "remote_write_error"


class RunnerInfo(WireModel):
    hostname: str
    cpu_count: int
    k6_version: str


class RunResult(WireModel):
    run_id: str
    status: RunStatus
    outcome: RunOutcome
    exit_code: int
    started_at: str
    finished_at: str
    duration_ms: int
    k6_version: str = ""
    template_version: str = ""
    script_sha256: str = ""
    summary: dict[str, Any] | None = None
    flags: list[ResultFlag] = Field(default_factory=list)
    error_message: str = ""
    log_tail: str = ""
    runner: RunnerInfo | None = None
