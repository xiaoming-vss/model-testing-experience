"""Validate Worker lease and task identities."""

from datetime import UTC, datetime

from testing_agent.core.enums import RUN_TERMINAL_STATUSES
from testing_agent.core.errors import ErrBadRequest, ErrForbidden, ErrWorkerLeaseLost
from testing_agent.core.utc import as_utc
from testing_agent.schemas.workers import WorkerTaskEventRequest


def ensure_worker_match(task, worker_id: str | None) -> None:
    if not worker_id or not worker_id.strip():
        raise ErrBadRequest()
    if not task.worker_id or task.worker_id != worker_id:
        raise ErrForbidden()
    # 409, not 400: workers end the execution on it, while a 400 is a request they sent wrong.
    if task.status not in {"claimed", "running", "stopping"}:
        raise ErrWorkerLeaseLost()
    lease = getattr(task, "lease_expires_at", None)
    if lease is not None:
        lease = as_utc(lease)
        if lease <= datetime.now(UTC):
            raise ErrWorkerLeaseLost()


def ensure_task_id(task, body: WorkerTaskEventRequest) -> None:
    if body.task_id and body.task_id != task.task_id:
        raise ErrBadRequest()


def is_late_event(task, body: WorkerTaskEventRequest, *, from_owner_only: bool = True) -> bool:
    """Tell whether an event arrived for a task that has already finished.

    A task id that does not match the route is always refused. By default so is
    any worker other than the one recorded on the task; a heartbeat only echoes
    the ids it was given, so it is accepted from whoever sends it.
    """
    ensure_task_id(task, body)
    if task.status not in RUN_TERMINAL_STATUSES:
        return False
    if from_owner_only and (not body.worker_id or task.worker_id != body.worker_id):
        raise ErrForbidden()
    return True
