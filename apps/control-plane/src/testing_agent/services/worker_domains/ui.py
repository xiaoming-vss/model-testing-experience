from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.enums import RunStatus
from testing_agent.core.errors import ErrBadRequest, ErrNotFound
from testing_agent.domain.worker_context import UiWorkerContext
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_case_run import UiTestCaseRun
from testing_agent.models.ui_test_suite_run import UiTestSuiteRun, UiTestSuiteRunItem
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.worker_task import WorkerTaskRepository
from testing_agent.schemas.workers import (
    WorkerTaskEventRequest,
)
from testing_agent.services.ui_execution_payload import (
    ui_case_payload as ui_case_model_payload,
)
from testing_agent.services.ui_execution_payload import (
    ui_suite_payload as ui_suite_model_payload,
)
from testing_agent.services.worker_domains.events import (
    final_run_status,
    parse_event_time,
    task_payload,
)


def ui_suite_payload(suite: Any | None) -> dict[str, Any]:
    return ui_suite_model_payload(suite)


async def ui_case_payload(session: AsyncSession, case_id: str) -> dict[str, Any]:
    case = await session.scalar(select(UiTestCase).where(UiTestCase.case_id == case_id))
    return ui_case_model_payload(case)


async def update_ui_item_counts(session: AsyncSession, suite_run_id: str) -> None:
    items = (
        await session.scalars(
            select(UiTestSuiteRunItem).where(UiTestSuiteRunItem.suite_run_id == suite_run_id)
        )
    ).all()
    run = await session.scalar(
        select(UiTestSuiteRun).where(UiTestSuiteRun.suite_run_id == suite_run_id)
    )
    if run:
        run.success_count = sum(1 for item in items if item.status in {"success", "passed"})
        run.failed_count = sum(1 for item in items if item.status == RunStatus.FAILED.value)
        run.error_count = sum(1 for item in items if item.status == RunStatus.ERROR.value)
        run.skipped_count = sum(1 for item in items if item.status == RunStatus.SKIPPED.value)


async def build_snapshot(
    session: AsyncSession, task: WorkerTask, context: UiWorkerContext
) -> dict[str, Any]:
    payload = task_payload(task, context)
    if task.task_type == "suite_run":
        run = await session.scalar(
            select(UiTestSuiteRun).where(UiTestSuiteRun.suite_run_id == task.run_id)
        )
        suite_run = dict(run.snapshot_json or {}) if run else {}
        if run:
            items = (
                await session.scalars(
                    select(UiTestSuiteRunItem)
                    .where(UiTestSuiteRunItem.suite_run_id == task.run_id)
                    .order_by(UiTestSuiteRunItem.order_no)
                )
            ).all()
            suite_run["items"] = [
                dict(item.snapshot_json or {})
                or {
                    "itemId": item.item_id,
                    "caseId": item.case_id,
                    "orderNo": item.order_no,
                    "continueOnFailure": item.continue_on_failure,
                    "status": item.status,
                }
                for item in items
            ]
        payload["suiteRun"] = suite_run
    else:
        run = await session.scalar(select(UiTestCaseRun).where(UiTestCaseRun.run_id == task.run_id))
        payload["caseRun"] = dict(run.snapshot_json or {}) if run else {}
    return payload


async def complete_run(
    session: AsyncSession, task: WorkerTask, body: WorkerTaskEventRequest
) -> None:
    status = final_run_status(body.status)
    if task.task_type == "suite_run":
        run = await session.scalar(
            select(UiTestSuiteRun).where(UiTestSuiteRun.suite_run_id == task.run_id)
        )
        if run:
            run.trace_path = body.trace_path or ""
            run.status = status
            run.error_message = body.error_message or ""
            run.finished_at = parse_event_time(body.finished_at) or datetime.now(UTC)
            if body.duration_ms is not None:
                run.duration_ms = body.duration_ms
    else:
        run = await session.scalar(select(UiTestCaseRun).where(UiTestCaseRun.run_id == task.run_id))
        if run:
            run.trace_path = body.trace_path or ""
            run.status = status
            run.step_results_json = body.step_results or run.step_results_json
            run.error_message = body.error_message or ""
            run.finished_at = parse_event_time(body.finished_at) or datetime.now(UTC)
            if body.duration_ms is not None:
                run.duration_ms = body.duration_ms


async def start_item(
    repository: WorkerTaskRepository, task: WorkerTask, item_id: str, body: WorkerTaskEventRequest
) -> None:
    item = await repository.get_ui_item(item_id)
    if item is None:
        raise ErrNotFound()
    if item.suite_run_id != task.run_id:
        raise ErrBadRequest()
    item.status = RunStatus.RUNNING.value
    item.started_at = parse_event_time(body.started_at) or datetime.now(UTC)


async def complete_item(
    repository: WorkerTaskRepository, task: WorkerTask, item_id: str, body: WorkerTaskEventRequest
) -> str:
    item = await repository.get_ui_item(item_id)
    if item is None:
        raise ErrNotFound()
    if item.suite_run_id != task.run_id:
        raise ErrBadRequest()
    item.status = final_run_status(body.status)
    item.snapshot_json = body.snapshot_json or item.snapshot_json
    item.step_results_json = body.step_results or item.step_results_json
    item.error_message = body.error_message or ""
    item.finished_at = parse_event_time(body.finished_at) or datetime.now(UTC)
    if body.duration_ms is not None:
        item.duration_ms = body.duration_ms
    await update_ui_item_counts(repository.session, item.suite_run_id)
    return item.status


async def mark_started(
    session: AsyncSession, task: WorkerTask, started_at: datetime | None
) -> None:
    if task.task_type == "suite_run":
        run = await session.scalar(
            select(UiTestSuiteRun).where(UiTestSuiteRun.suite_run_id == task.run_id)
        )
    else:
        run = await session.scalar(select(UiTestCaseRun).where(UiTestCaseRun.run_id == task.run_id))
    if run:
        run.status = RunStatus.RUNNING.value
        if getattr(run, "started_at", None) is None:
            run.started_at = started_at or datetime.now(UTC)
