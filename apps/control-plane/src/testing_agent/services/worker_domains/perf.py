"""Performance execution lifecycle updates owned by the perf domain."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.enums import PERF_RUN_TERMINAL_STATUSES, PerfRunStatus
from testing_agent.models.perf_run import PerfRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.perf_run import PerfRunRepository
from testing_agent.schemas.workers import WorkerTaskEventRequest


async def get_run(session: AsyncSession, task: WorkerTask) -> PerfRun | None:
    return await PerfRunRepository(session).get_run(task.run_id)


async def expire(session: AsyncSession, task: WorkerTask, message: str) -> None:
    now = datetime.now(UTC)
    task.status = "failed"
    task.error_message = message
    task.finished_at = now
    task.lease_expires_at = now
    run = await get_run(session, task)
    if run is None or run.status in PERF_RUN_TERMINAL_STATUSES:
        return
    run.status = PerfRunStatus.FAILED.value
    run.outcome = "execution_error"
    run.error_message = message
    run.finished_at = now


async def complete_run(
    session: AsyncSession, task: WorkerTask, body: WorkerTaskEventRequest
) -> None:
    """Generic completion path used by the lease reaper."""
    run = await get_run(session, task)
    if run is None or run.status in PERF_RUN_TERMINAL_STATUSES:
        return
    now = datetime.now(UTC)
    if body.status in {"failed", "error"}:
        run.status = PerfRunStatus.FAILED.value
        run.outcome = "execution_error"
    elif body.status == "canceled":
        run.status = PerfRunStatus.CANCELED.value
        run.outcome = "stopped"
    else:
        run.status = PerfRunStatus.FAILED.value
        run.outcome = "execution_error"
    run.error_message = body.error_message or run.error_message
    run.finished_at = now
