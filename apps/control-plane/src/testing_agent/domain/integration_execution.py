"""Pure integration execution rules; remote writes are never inferred from a lease."""

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class JobStatus(StrEnum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    UNKNOWN = "unknown"
    CANCELED = "canceled"
    QUARANTINED = "quarantined"


class StepStatus(StrEnum):
    PENDING = "pending"
    WRITE_INTENT = "write_intent"
    SUCCEEDED = "succeeded"
    NOOP = "noop"
    FAILED = "failed"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"
    CANCELED = "canceled"


ACTIVE_JOB_STATUSES = (JobStatus.QUEUED, JobStatus.CLAIMED, JobStatus.RUNNING)
SUCCESS_STEP_STATUSES = (StepStatus.SUCCEEDED, StepStatus.NOOP)
UNRESOLVED_STEP_STATUSES = (StepStatus.WRITE_INTENT, StepStatus.UNKNOWN)


def digest(value: Any) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode()).hexdigest()


def same_result(kind: str, left: dict[str, Any], right: dict[str, Any]) -> bool:
    if kind != "update_fields":
        return left == right
    expected = {"openedBuild", "assignedTo"}
    if set(left) != expected or set(right) != expected:
        return False
    builds = [left["openedBuild"], right["openedBuild"]]
    if any(
        not isinstance(values, list) or any(not isinstance(v, str) for v in values)
        for values in builds
    ):
        return False
    return set(builds[0]) == set(builds[1]) and left["assignedTo"] == right["assignedTo"]


def utc(value: datetime) -> datetime:
    # MySQL/SQLite return naive DateTime values even when timezone=True.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def aggregate(statuses: list[str], *, canceled: bool = False) -> JobStatus:
    if StepStatus.UNKNOWN in statuses:
        return JobStatus.UNKNOWN
    if StepStatus.WRITE_INTENT in statuses:
        return JobStatus.RUNNING
    if canceled:
        return JobStatus.CANCELED
    if StepStatus.PENDING in statuses:
        return JobStatus.RUNNING
    if statuses and all(state in SUCCESS_STEP_STATUSES for state in statuses):
        return JobStatus.SUCCEEDED
    if any(state in SUCCESS_STEP_STATUSES for state in statuses):
        return JobStatus.PARTIAL
    return JobStatus.FAILED


def require_safe_snapshot(value: Any) -> None:
    """Fail closed on accidental persistence of access material."""
    forbidden = {"token", "apikey", "authorization", "password", "downloadurl", "signedurl"}
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower().replace("_", "").replace("-", "")
            if any(normalized.endswith(name) for name in forbidden):
                raise ValueError("Integration history cannot contain access material")
            require_safe_snapshot(nested)
    elif isinstance(value, list):
        for nested in value:
            require_safe_snapshot(nested)
    elif isinstance(value, str) and (
        "x-amz-signature=" in value.lower() or "x-amz-credential=" in value.lower()
    ):
        raise ValueError("Integration history cannot contain signed URLs")
