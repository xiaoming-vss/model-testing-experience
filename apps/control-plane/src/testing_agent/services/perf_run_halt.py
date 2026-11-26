"""Stop one perf run and its queue task; shared by the single-run and suite services."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from testing_agent.core.enums import PerfRunStatus
from testing_agent.models.perf_run import PerfRun
from testing_agent.models.worker_task import WorkerTask

STOP_MESSAGE = "用户已停止运行"


async def halt_perf_run(session, run: PerfRun) -> bool:
    """Cancel a queued run that was never claimed, or ask its claimed task to stop.

    Returns True when the run reached a terminal state here.
    """
    now = datetime.now(UTC)
    task = await session.scalar(
        select(WorkerTask)
        .where(WorkerTask.domain == "perf", WorkerTask.run_id == run.run_id)
        .with_for_update()
    )
    if run.status == PerfRunStatus.QUEUED.value and (task is None or task.status == "pending"):
        run.status = PerfRunStatus.CANCELED.value
        run.outcome = "stopped"
        run.error_message = STOP_MESSAGE
        run.finished_at = now
        if task is not None:
            task.status = "canceled"
            task.finished_at = now
            task.error_message = STOP_MESSAGE
        return True
    run.status = PerfRunStatus.STOPPING.value
    if task is not None:
        task.status = "stopping"
    return False
