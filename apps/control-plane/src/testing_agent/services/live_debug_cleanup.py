"""Deliver and retire ephemeral single-API debug runs."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.http_diagnostics import safe_exception_trace
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.schemas.api_run import ApiCaseRunResponse
from testing_agent.services.test_run_notifications import has_run_subscribers, notify_run_finished

logger = logging.getLogger(__name__)


async def finish_api_debug(session: AsyncSession, task_id: str) -> bool:
    """Best-effort delivery followed by durable deletion of a terminal debug run."""
    task = await session.scalar(
        select(WorkerTask)
        .where(WorkerTask.domain == "api", WorkerTask.task_id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        task is None
        or task.task_type != "api_case_debug"
        or task.status not in {"success", "failed", "error", "canceled"}
    ):
        return False
    run = await session.scalar(select(ApiCaseRun).where(ApiCaseRun.run_id == task.run_id))
    if run is None or run.trigger_type != "live_debug":
        return False
    result = ApiCaseRunResponse.model_validate(run).model_dump(by_alias=True, mode="json")
    result["success"] = run.status == "success"
    await notify_run_finished("api", run.run_id, result)
    await session.delete(task)
    await session.delete(run)
    await session.commit()
    return True


@dataclass
class DebugCleanupCursor:
    """Process-local scan position; failed entries are revisited after a full pass."""

    after_id: int = 0
    through_id: int = 0


async def _start_cleanup_scan(session: AsyncSession, cursor: DebugCleanupCursor | None) -> None:
    if cursor is not None and not cursor.through_id:
        cursor.through_id = await session.scalar(select(func.max(WorkerTask.id))) or 0


async def recover_api_debug_runs(
    session: AsyncSession, limit: int = 100, *, cursor: DebugCleanupCursor | None = None
) -> int:
    """Retire terminal live runs left behind by a process crash."""
    await _start_cleanup_scan(session, cursor)
    rows = (
        await session.execute(
            select(WorkerTask.id, WorkerTask.task_id)
            .join(ApiCaseRun, ApiCaseRun.run_id == WorkerTask.run_id)
            .where(
                WorkerTask.domain == "api",
                WorkerTask.task_type == "api_case_debug",
                WorkerTask.status.in_(["success", "failed", "error", "canceled"]),
                ApiCaseRun.trigger_type == "live_debug",
                WorkerTask.id > (cursor.after_id if cursor else 0),
                WorkerTask.id <= cursor.through_id if cursor else true(),
            )
            .order_by(WorkerTask.id)
            .limit(limit)
        )
    ).all()
    if cursor is not None:
        cursor.after_id = rows[-1][0] if len(rows) == limit else 0
        if not cursor.after_id:
            cursor.through_id = 0
    return await _recover_debug_records(session, [row[1] for row in rows], "api", finish_api_debug)


_ui_delivery_slots = asyncio.Semaphore(2)
_background_deliveries: set[asyncio.Task] = set()


def schedule_ui_debug_delivery(task_id: str) -> None:
    """Do not hold a Worker slot while a browser receives a large artifact."""
    from testing_agent.db.session import AsyncSessionLocal

    async def deliver() -> None:
        try:
            async with AsyncSessionLocal() as session:
                await finish_ui_debug(session, task_id)
        except Exception as exc:
            # The terminal run remains durable and the monitor will retry it.
            logger.warning("Debug delivery failed: %s", type(exc).__name__)

    task = asyncio.create_task(deliver())
    _background_deliveries.add(task)
    task.add_done_callback(_background_deliveries.discard)


async def finish_ui_debug(session: AsyncSession, task_id: str) -> bool:
    """Bound concurrent artifact deliveries across UI debug completions."""
    async with _ui_delivery_slots:
        return await _finish_ui_debug(session, task_id)


async def _finish_ui_debug(session: AsyncSession, task_id: str) -> bool:
    """Deliver an ephemeral UI result and retire its records and S3 artifacts."""
    from datetime import UTC, datetime, timedelta

    from testing_agent.core.config import get_settings
    from testing_agent.models.stored_file import StoredFile
    from testing_agent.models.ui_test_case_run import UiTestCaseRun
    from testing_agent.services.live_debug_transfer import request_ui_artifact_delivery
    from testing_agent.services.stored_file import StoredFileService
    from testing_agent.services.ui_test_case_run import dump_case_run

    task = await session.scalar(
        select(WorkerTask)
        .where(WorkerTask.domain == "ui", WorkerTask.task_id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        task is None
        or task.task_type != "case_debug"
        or task.status not in {"success", "failed", "error", "canceled"}
    ):
        return False
    run = await session.scalar(select(UiTestCaseRun).where(UiTestCaseRun.run_id == task.run_id))
    if run is None or run.trigger_type != "live_debug":
        return False
    result = dump_case_run(run)
    files = list(
        await session.scalars(
            select(StoredFile)
            .where(
                StoredFile.resource_type == "ui_worker_task",
                StoredFile.resource_id == task_id,
                StoredFile.status.in_(["pending", "ready", "attached", "archived", "deleting"]),
            )
            .with_for_update()
        )
    )
    storage_service = StoredFileService(session, get_settings().s3)
    requested: set[str] = set()
    trace = result.get("tracePath")
    if isinstance(trace, str) and trace:
        requested.add(trace)
    for step in result.get("stepResults") or []:
        if isinstance(step, dict):
            path = step.get("screenshotPath")
            if isinstance(path, str) and path:
                requested.add(path)
    manifest = []
    deliver_artifacts = bool(requested) and await has_run_subscribers("ui", run.run_id)
    for file in files:
        path = f"/v1/files/{file.file_id}/download"
        if path in requested and deliver_artifacts:
            manifest.append(
                {
                    "path": path,
                    "bucket": file.bucket,
                    "key": file.object_key,
                    "media": "image/png"
                    if file.filename.lower().endswith(".png")
                    else "application/zip",
                    "size": file.size,
                    "sha256": file.sha256,
                }
            )
    failed = (
        await request_ui_artifact_delivery(run.run_id, manifest) if manifest else set(requested)
    )
    paths = {item["path"]: item["path"] for item in manifest if item["path"] not in failed}
    for file in files:
        file.status = "deleting"
        file.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
    if result.get("tracePath"):
        result["tracePath"] = paths.get(result["tracePath"], "")
    for step in result.get("stepResults") or []:
        if isinstance(step, dict) and step.get("screenshotPath"):
            step["screenshotPath"] = paths.get(step["screenshotPath"], "")
    if any(not paths.get(path) for path in requested):
        result["errorMessage"] = (result.get("errorMessage") or "") + " 部分临时产物读取失败"
    await notify_run_finished("ui", run.run_id, result)
    await session.delete(task)
    await session.delete(run)
    await session.commit()
    if files:
        try:
            await storage_service.cleanup()
        except Exception as exc:
            # Deleting rows are durable cleanup work and will be retried by the monitor.
            logger.warning("Debug artifact cleanup failed: %s", type(exc).__name__)
            await session.rollback()
    return True


async def recover_ui_debug_runs(
    session: AsyncSession, limit: int = 100, *, cursor: DebugCleanupCursor | None = None
) -> int:
    """Retire terminal UI debug runs left behind by a process crash."""
    from testing_agent.models.ui_test_case_run import UiTestCaseRun

    await _start_cleanup_scan(session, cursor)
    rows = (
        await session.execute(
            select(WorkerTask.id, WorkerTask.task_id)
            .join(UiTestCaseRun, UiTestCaseRun.run_id == WorkerTask.run_id)
            .where(
                WorkerTask.domain == "ui",
                WorkerTask.task_type == "case_debug",
                WorkerTask.status.in_(["success", "failed", "error", "canceled"]),
                UiTestCaseRun.trigger_type == "live_debug",
                WorkerTask.id > (cursor.after_id if cursor else 0),
                WorkerTask.id <= cursor.through_id if cursor else true(),
            )
            .order_by(WorkerTask.id)
            .limit(limit)
        )
    ).all()
    if cursor is not None:
        cursor.after_id = rows[-1][0] if len(rows) == limit else 0
        if not cursor.after_id:
            cursor.through_id = 0
    return await _recover_debug_records(session, [row[1] for row in rows], "ui", finish_ui_debug)


async def _recover_debug_records(
    session: AsyncSession,
    task_ids: list[str],
    domain: str,
    finish: Callable[[AsyncSession, str], Awaitable[bool]],
) -> int:
    """A broken record must not prevent other transient results being retired."""
    recovered = 0
    for task_id in task_ids:
        try:
            recovered += bool(await finish(session, task_id))
        except Exception as exc:
            await session.rollback()
            logger.error(
                "Debug cleanup failed for task %s; retrying later (%s)",
                task_id,
                type(exc).__name__,
                extra={
                    "task_id": task_id,
                    "task_domain": domain,
                    "stack_trace": safe_exception_trace(exc),
                },
            )
    return recovered
