from typing import Any, Literal

from pydantic import Field

from testing_agent_integration_worker.schemas.job import Access, Identity, WireModel


class RemoteResult(WireModel):
    remote_bug_id: int | None = Field(default=None, gt=0, le=2_147_483_647)
    remote_file_id: int | None = Field(default=None, gt=0, le=2_147_483_647)
    description_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    opened_build: list[str] | None = Field(default=None, max_length=50)
    assigned_to: str | None = Field(default=None, max_length=100)
    error_code: (
        Literal[
            "remote_rejected",
            "remote_unavailable",
            "remote_uncertain",
            "baseline_changed",
            "input_changed",
            "access_revoked",
            "dependency_failed",
            "lease_lost",
            "canceled",
        ]
        | None
    ) = None


class ResultEvent(Identity):
    event_id: str
    operation_id: str
    status: Literal["succeeded", "failed", "unknown"]
    result: RemoteResult
    remote_duration_ms: int | None = Field(default=None, strict=True, ge=0, le=86_400_000)


class Operation(WireModel):
    tool: Literal["post_bugs", "upload_bug_attachment", "put_bugs_bugID"]
    arguments: dict[str, Any] = Field(repr=False)
    timeout_seconds: float = Field(gt=0, le=180)


class Permit(WireModel):
    operation_id: str
    status: str
    write_allowed: bool
    permit_seconds: float | None = None
    access: Access | None = Field(default=None, repr=False)
    operation: Operation | None = Field(default=None, repr=False)
    mapping: dict[str, Any] | None = Field(default=None, repr=False)
    job_id: str | None = None
    job_status: str | None = None
    task_type: str | None = None
    protocol_version: int | None = None
    result: dict[str, Any] | None = Field(default=None, repr=False)
