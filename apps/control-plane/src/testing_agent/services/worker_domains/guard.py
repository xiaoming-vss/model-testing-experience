"""Validate Worker lease and task identities."""

from datetime import UTC, datetime

from testing_agent.core.errors import ErrBadRequest, ErrForbidden
from testing_agent.schemas.workers import WorkerTaskEventRequest


def ensure_worker_match(task, worker_id: str | None) -> None:
    if not worker_id or not worker_id.strip():
        raise ErrBadRequest()
    if not task.worker_id or task.worker_id != worker_id:
        raise ErrForbidden()
    if task.status not in {"claimed", "running", "stopping"}:
        raise ErrBadRequest()
    lease = getattr(task, "lease_expires_at", None)
    if lease is not None:
        if lease.tzinfo is None:
            lease = lease.replace(tzinfo=UTC)
        if lease <= datetime.now(UTC):
            raise ErrBadRequest()


def ensure_task_id(task, body: WorkerTaskEventRequest) -> None:
    if body.task_id and body.task_id != task.task_id:
        raise ErrBadRequest()
