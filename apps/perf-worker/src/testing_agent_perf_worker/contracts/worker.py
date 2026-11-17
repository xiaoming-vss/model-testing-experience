"""Strict wire models for the control-plane perf worker protocol."""

from __future__ import annotations

from pydantic import Field, field_validator

from .spec import RunSpec, WireModel


class DataFileRef(WireModel):
    file_id: str
    filename: str
    size: int = Field(ge=0)
    sha256: str

    @field_validator("filename")
    @classmethod
    def _safe_filename(cls, value: str) -> str:
        if not value or "/" in value or "\\" in value or value in {".", ".."}:
            raise ValueError("数据文件名不合法")
        return value

    @field_validator("sha256")
    @classmethod
    def _sha256(cls, value: str) -> str:
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError("数据文件 sha256 不合法")
        return value


class ClaimRequest(WireModel):
    worker_id: str


class ClaimResponse(WireModel):
    task_id: str
    task_type: str
    run_id: str
    status: str
    lease_seconds: int = Field(ge=1)


class SnapshotResponse(WireModel):
    task_id: str
    run_id: str
    case_name: str
    run_spec: RunSpec
    data_files: list[DataFileRef] = Field(default_factory=list)
    lease_seconds: int = Field(ge=1)


class StartedRequest(WireModel):
    worker_id: str
    started_at: str


class HeartbeatRequest(WireModel):
    worker_id: str


class HeartbeatResponse(WireModel):
    stop_requested: bool
    lease_seconds: int = Field(ge=0)


class ControlResponse(WireModel):
    stop_requested: bool
