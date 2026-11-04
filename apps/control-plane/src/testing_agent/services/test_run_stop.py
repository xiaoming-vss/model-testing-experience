"""Stop API/UI executions without replaying external operations."""

from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrForbidden, ErrNotFound
from testing_agent.models.api_collection_run import ApiCollectionRunItem
from testing_agent.models.ui_test_suite_run import UiTestSuiteRunItem
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.api_case import ApiCaseService
from testing_agent.services.api_collection_run import ApiCollectionRunService
from testing_agent.services.test_run_notifications import notify_run_changed, notify_task_control
from testing_agent.services.ui_test_case_run import UiTestCaseRunService

RunKind = Literal["api-case", "api-collection", "ui-case", "ui-suite"]


async def stop_run(
    kind: RunKind,
    run_id: str,
    user_id: str,
    session: AsyncSession,
    api_cases: ApiCaseService,
    api_collections: ApiCollectionRunService,
    ui_runs: UiTestCaseRunService,
) -> dict:
    run: Any
    if kind == "api-case":
        run = await api_cases.repository.get_run(run_id)
        if run is None:
            raise ErrNotFound()
        await api_cases.get_accessible_context(user_id, run.case_id, action="execute")
        if run.trigger_user_id != user_id:
            raise ErrForbidden()
    elif kind == "api-collection":
        run = await api_collections.repository.get_run(run_id)
        if run is None:
            raise ErrNotFound()
        await api_collections.get_accessible_context(user_id, run.collection_id, action="execute")
    elif kind == "ui-case":
        run = await ui_runs.repository.get_case_run(run_id)
        if run is None:
            raise ErrNotFound()
        await ui_runs.get_accessible_suite(user_id, run.suite_id, action="execute")
        if run.trigger_user_id != user_id:
            raise ErrForbidden()
    else:
        run = await ui_runs.repository.get_suite_run(run_id)
        if run is None:
            raise ErrNotFound()
        await ui_runs.get_accessible_suite(user_id, run.suite_id, action="execute")

    domain = "api" if kind.startswith("api-") else "ui"
    task_type = {
        "api-case": "api_case_debug",
        "api-collection": "api_collection_run",
        "ui-case": "case_debug",
        "ui-suite": "suite_run",
    }[kind]
    task = await session.scalar(
        select(WorkerTask)
        .where(
            WorkerTask.domain == domain,
            WorkerTask.run_id == run_id,
            WorkerTask.task_type == task_type,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if task is None:
        raise ErrNotFound()
    await session.refresh(run)
    if task.status == "pending":
        now = datetime.now(UTC)
        task.status = run.status = "canceled"
        task.finished_at = run.finished_at = now
        if kind in {"api-collection", "ui-suite"}:
            model: Any = ApiCollectionRunItem if domain == "api" else UiTestSuiteRunItem
            field = model.collection_run_id if domain == "api" else model.suite_run_id
            items: list[Any] = list(
                (await session.scalars(select(model).where(field == run_id))).all()
            )
            for item in items:
                item.status = "skipped"
                item.error_message = "运行已停止"
                item.finished_at = now
            run.skipped_count = len(items)
    elif task.status in {"claimed", "running"}:
        task.status = run.status = "stopping"
    elif task.status != "stopping":
        return {"status": run.status}
    await session.commit()
    await notify_run_changed(domain, run_id)
    status, task_id = task.status, task.task_id
    if status == "stopping":
        await notify_task_control(task_id)
    elif kind == "api-case" and status == "canceled" and run.trigger_type == "live_debug":
        from testing_agent.services.live_debug_cleanup import finish_api_debug

        await finish_api_debug(session, task_id)
    elif kind == "ui-case" and status == "canceled" and run.trigger_type == "live_debug":
        from testing_agent.services.live_debug_cleanup import finish_ui_debug

        await finish_ui_debug(session, task_id)
    return {"status": status}


async def finish_stopped_items(
    session: AsyncSession, task: WorkerTask, *, interrupted: bool = False, reason: str = ""
) -> None:
    """Close unfinished suite items while retaining completed and partial results."""
    model: Any
    field: Any
    if task.task_type == "api_collection_run":
        model, field = ApiCollectionRunItem, ApiCollectionRunItem.collection_run_id
    elif task.task_type == "suite_run":
        model, field = UiTestSuiteRunItem, UiTestSuiteRunItem.suite_run_id
    else:
        return
    items: list[Any] = list(
        (await session.scalars(select(model).where(field == task.run_id))).all()
    )
    now = datetime.now(UTC)
    for item in items:
        if item.status in {"pending", "queued", "claimed"}:
            item.status = "skipped"
            item.error_message = reason or ("Worker 失联" if interrupted else "运行已停止")
            item.finished_at = now
        elif item.status == "running":
            item.status = "error" if interrupted else "canceled"
            item.error_message = reason or ("Worker 失联" if interrupted else "运行已停止")
            if task.domain == "ui":
                from testing_agent.services.worker_domains.ui import close_running_steps

                item.step_results_json = close_running_steps(
                    item.step_results_json, item.status, item.error_message
                )
            item.finished_at = now
    await session.flush()
    if task.domain == "ui":
        from testing_agent.services.worker_domains.ui import update_ui_item_counts

        await update_ui_item_counts(session, task.run_id)
    elif task.domain == "api":
        from testing_agent.services.worker_domains.api import update_item_counts

        await update_item_counts(session, task.run_id)
