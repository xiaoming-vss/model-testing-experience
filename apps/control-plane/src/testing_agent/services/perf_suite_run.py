from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol, cast

from testing_agent.core.enums import PERF_RUN_TERMINAL_STATUSES, PerfRunStatus
from testing_agent.core.errors import ErrBadRequest, ErrForbidden, ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.core.utc import as_utc
from testing_agent.models.perf_case import PerfCase
from testing_agent.models.perf_run import PerfRun
from testing_agent.models.perf_suite import PerfSuite
from testing_agent.models.perf_suite_run import PerfSuiteRun, PerfSuiteRunItem
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.perf_case import PerfCaseRepository
from testing_agent.repositories.perf_run import PerfRunRepository
from testing_agent.repositories.perf_suite import PerfSuiteRepository
from testing_agent.repositories.perf_suite_run import PerfSuiteRunRepository
from testing_agent.schemas.perf_run import PerfRunCreate
from testing_agent.schemas.perf_suite_run import (
    PerfSuiteItemStatus,
    PerfSuiteRunCreate,
    PerfSuiteRunItemResponse,
    PerfSuiteRunResponse,
    PerfSuiteRunSummaryResponse,
)
from testing_agent.services.perf_run_halt import STOP_MESSAGE, halt_perf_run
from testing_agent.services.project_access import ProjectAction, require_project_id

SUITE_TERMINAL_STATUSES = {
    PerfRunStatus.COMPLETED.value,
    PerfRunStatus.FAILED.value,
    PerfRunStatus.STOPPED.value,
    PerfRunStatus.CANCELED.value,
}


def _child_item_status(status: str) -> str:
    if status == PerfRunStatus.COMPLETED.value:
        return "completed"
    if status == PerfRunStatus.FAILED.value:
        return "failed"
    if status in {PerfRunStatus.STOPPED.value, PerfRunStatus.CANCELED.value}:
        return "canceled"
    return "failed"


class PerfRunPreparer(Protocol):
    """Freeze one child run without importing the single-run service (avoids cycles)."""

    async def prepare(
        self,
        user_id: str,
        case: PerfCase,
        body: PerfRunCreate | PerfSuiteRunCreate,
        run_id: str,
        suite_run_id: str = "",
    ) -> PerfRun: ...


class PerfSuiteRunService:
    def __init__(
        self,
        repository: PerfSuiteRunRepository,
        *,
        suites: PerfSuiteRepository,
        cases: PerfCaseRepository,
        runs: PerfRunRepository,
        perf_runs: PerfRunPreparer | None = None,
    ) -> None:
        self.repository = repository
        self.suites = suites
        self.cases = cases
        self.runs = runs
        self.perf_runs = perf_runs

    def _enqueue(self, run_id: str) -> None:
        self.repository.session.add(
            WorkerTask(
                domain="perf",
                task_id=new_id(),
                task_type="perf_run",
                run_id=run_id,
                status="pending",
            )
        )

    async def _accessible_suite(
        self, user_id: str, suite_id: str, *, action: ProjectAction, for_update: bool = False
    ) -> PerfSuite:
        suite = await self.suites.get_suite(suite_id, for_update=for_update)
        if suite is None:
            raise ErrNotFound()
        await require_project_id(self.repository.session, user_id, suite.project_id, action=action)
        return suite

    async def _accessible_run(
        self, user_id: str, suite_run_id: str, *, action: ProjectAction
    ) -> PerfSuiteRun:
        run = await self.repository.get_run(suite_run_id, for_update=action == "execute")
        if run is None:
            raise ErrNotFound()
        await require_project_id(self.repository.session, user_id, run.project_id, action=action)
        return run

    def _summary(self, run: PerfSuiteRun) -> dict[str, Any]:
        response = PerfSuiteRunSummaryResponse(
            suite_run_id=run.suite_run_id,
            suite_id=run.suite_id,
            project_id=run.project_id,
            sprint_id=run.sprint_id,
            sprint_name=run.sprint_name,
            suite_name=run.suite_name,
            environment_id=run.environment_id,
            environment_name=run.environment_name,
            monitoring_connection_id=run.monitoring_connection_id,
            monitoring_connection_name=run.monitoring_connection_name,
            trigger_user_id=run.trigger_user_id,
            trigger_type=run.trigger_type,
            status=cast(PerfRunStatus, run.status),
            outcome=run.outcome,
            total_count=run.total_count,
            completed_count=run.completed_count,
            failed_count=run.failed_count,
            skipped_count=run.skipped_count,
            error_message=run.error_message,
            started_at=run.started_at,
            finished_at=run.finished_at,
            duration_ms=run.duration_ms,
            created_at=run.created_at,
        )
        return response.model_dump(by_alias=True, mode="json")

    def _item_payload(self, item: PerfSuiteRunItem, child: PerfRun | None) -> dict[str, Any]:
        status = item.status
        outcome = item.outcome
        error_message = item.error_message
        started_at = item.started_at
        finished_at = item.finished_at
        duration_ms = item.duration_ms
        summary = None
        load = None
        log_tail = ""
        flags: list[Any] = []
        k6_version = ""
        if child is not None:
            if item.status == "queued" and child.status not in {
                PerfRunStatus.QUEUED.value,
            }:
                status = child.status
            outcome = child.outcome or outcome
            error_message = child.error_message or error_message
            started_at = started_at or child.started_at
            finished_at = finished_at or child.finished_at
            duration_ms = duration_ms or child.duration_ms
            summary = child.summary_json
            spec_case = (child.spec_json or {}).get("case")
            if isinstance(spec_case, dict) and isinstance(spec_case.get("load"), dict):
                load = spec_case["load"]
            log_tail = child.log_tail
            flags = child.flags_json or []
            k6_version = child.k6_version
        response = PerfSuiteRunItemResponse(
            item_id=item.item_id,
            case_id=item.case_id,
            case_name=item.case_name,
            order_no=item.order_no,
            status=cast(PerfSuiteItemStatus, status),
            outcome=outcome,
            child_run_id=item.child_run_id,
            error_message=error_message,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            summary=summary,
            load=load,
            log_tail=log_tail,
            flags=flags,
            k6_version=k6_version,
        )
        return response.model_dump(by_alias=True, mode="json")

    async def _detail(self, run: PerfSuiteRun) -> dict[str, Any]:
        items = await self.repository.list_items(run.suite_run_id)
        children = await self.runs.list_by_ids(
            [item.child_run_id for item in items if item.child_run_id]
        )
        data = self._summary(run)
        data["items"] = [
            self._item_payload(item, children.get(item.child_run_id)) for item in items
        ]
        return PerfSuiteRunResponse.model_validate(data).model_dump(by_alias=True, mode="json")

    def _refresh_counts(self, run: PerfSuiteRun, items: list[PerfSuiteRunItem]) -> None:
        run.completed_count = sum(1 for item in items if item.status == "completed")
        run.failed_count = sum(1 for item in items if item.status == "failed")
        run.skipped_count = sum(1 for item in items if item.status == "skipped")
        run.total_count = len(items)

    def _finish(
        self,
        run: PerfSuiteRun,
        items: list[PerfSuiteRunItem],
        *,
        status: str,
        outcome: str,
    ) -> None:
        now = datetime.now(UTC)
        run.status = status
        run.outcome = outcome
        run.finished_at = now
        if run.started_at is not None:
            started_at = as_utc(run.started_at)
            run.duration_ms = max(0, int((now - started_at).total_seconds() * 1000))
        self._refresh_counts(run, items)

    async def _skip_unstarted(self, items: list[PerfSuiteRunItem]) -> None:
        """Skip items that can no longer be dispatched and cancel their prepared child runs."""
        now = datetime.now(UTC)
        unstarted = [item for item in items if item.status == "pending"]
        for item in unstarted:
            item.status = "skipped"
            item.finished_at = now
        children = await self.runs.list_by_ids(
            [item.child_run_id for item in unstarted], for_update=True
        )
        for child in children.values():
            if child.status == PerfRunStatus.QUEUED.value:
                child.status = PerfRunStatus.CANCELED.value
                child.outcome = "stopped"
                child.error_message = STOP_MESSAGE
                child.finished_at = now

    async def run(self, user_id: str, suite_id: str, body: PerfSuiteRunCreate) -> dict[str, Any]:
        if self.perf_runs is None:
            raise RuntimeError("PerfSuiteRunService.run requires PerfRunService")
        suite = await self._accessible_suite(user_id, suite_id, action="execute", for_update=True)
        if await self.repository.get_active_by_suite(suite_id) is not None:
            raise ErrBadRequest()
        all_cases = await self.cases.list_by_suite(suite_id)
        cases = [case for case in all_cases if case.invalidated_at is None]
        if not cases:
            raise ErrBadRequest()

        suite_run_id = new_id()
        prepared: list[tuple[PerfCase, PerfRun]] = []
        for case in cases:
            child = await self.perf_runs.prepare(user_id, case, body, new_id(), suite_run_id)
            child.trigger_type = "suite"
            prepared.append((case, child))

        first_run = prepared[0][1]
        suite_run = PerfSuiteRun(
            suite_run_id=suite_run_id,
            suite_id=suite.suite_id,
            project_id=suite.project_id,
            sprint_id=first_run.sprint_id,
            sprint_name=first_run.sprint_name,
            suite_name=suite.name,
            environment_id=first_run.environment_id,
            environment_name=first_run.environment_name,
            monitoring_connection_id=first_run.monitoring_connection_id,
            monitoring_connection_name=first_run.monitoring_connection_name,
            monitoring_snapshot_json=first_run.monitoring_snapshot_json,
            trigger_user_id=user_id,
            trigger_type="manual",
            status=PerfRunStatus.QUEUED.value,
            outcome="inconclusive",
            total_count=len(prepared),
            completed_count=0,
            failed_count=0,
            skipped_count=0,
            error_message="",
            duration_ms=0,
        )
        self.repository.add(suite_run)
        for index, (case, child) in enumerate(prepared, start=1):
            self.runs.add(child)
            self.repository.add_item(
                PerfSuiteRunItem(
                    item_id=new_id(),
                    suite_run_id=suite_run.suite_run_id,
                    case_id=case.case_id,
                    case_name=case.name,
                    order_no=index,
                    status="pending",
                    child_run_id=child.run_id,
                )
            )
        await self.repository.commit()
        await self.start_next(suite_run.suite_run_id)
        await self.repository.refresh(suite_run)
        return await self._detail(suite_run)

    async def start_next(self, suite_run_id: str) -> None:
        run = await self.repository.get_run(suite_run_id, for_update=True)
        if (
            run is None
            or run.status in SUITE_TERMINAL_STATUSES
            or run.status == PerfRunStatus.STOPPING.value
        ):
            return
        items = await self.repository.list_items(suite_run_id)
        for item in items:
            if item.status != "pending":
                continue
            child = await self.runs.get_run(item.child_run_id)
            if child is None:
                item.status = "failed"
                item.error_message = "子运行记录不存在"
                item.finished_at = datetime.now(UTC)
                continue
            now = datetime.now(UTC)
            item.status = "queued"
            run.status = PerfRunStatus.RUNNING.value
            run.started_at = run.started_at or now
            self._enqueue(child.run_id)
            await self.repository.commit()
            return

        active = [item for item in items if item.status in {"queued", "running"}]
        if not active:
            self._finish(
                run,
                items,
                status=PerfRunStatus.COMPLETED.value,
                outcome="inconclusive",
            )
            await self.repository.commit()

    async def on_child_started(self, child_run_id: str) -> None:
        item = await self.repository.get_item_by_child_run(child_run_id)
        if item is None:
            return
        run = await self.repository.get_run(item.suite_run_id, for_update=True)
        if (
            run is None
            or run.status in SUITE_TERMINAL_STATUSES
            or run.status == PerfRunStatus.STOPPING.value
        ):
            return
        now = datetime.now(UTC)
        item.status = "running"
        item.started_at = item.started_at or now
        if run.status == PerfRunStatus.QUEUED.value:
            run.status = PerfRunStatus.RUNNING.value
        run.started_at = run.started_at or now
        await self.repository.commit()

    async def on_child_completed(self, child_run_id: str) -> None:
        item = await self.repository.get_item_by_child_run(child_run_id)
        if item is None:
            return
        run = await self.repository.get_run(item.suite_run_id, for_update=True)
        if run is None or run.status in SUITE_TERMINAL_STATUSES:
            return
        child = await self.runs.get_run(child_run_id)
        items = await self.repository.list_items(run.suite_run_id)
        now = datetime.now(UTC)
        if child is not None:
            item.status = _child_item_status(child.status)
            item.outcome = child.outcome
            item.error_message = child.error_message
            item.started_at = item.started_at or child.started_at
            item.finished_at = child.finished_at or now
            item.duration_ms = child.duration_ms
        else:
            item.status = "failed"
            item.error_message = "子运行记录不存在"
            item.finished_at = now

        if run.status == PerfRunStatus.STOPPING.value or item.status == "canceled":
            await self._skip_unstarted(items)
            self._finish(
                run,
                items,
                status=PerfRunStatus.CANCELED.value,
                outcome="stopped",
            )
            await self.repository.commit()
            return

        if any(pending.status == "pending" for pending in items):
            self._refresh_counts(run, items)
            await self.repository.commit()
            await self.start_next(run.suite_run_id)
            return
        self._finish(
            run,
            items,
            status=PerfRunStatus.COMPLETED.value,
            outcome="inconclusive",
        )
        await self.repository.commit()

    async def reconcile_active(self) -> int:
        """Advance active suite runs whose completion hook was lost or interrupted."""
        repaired = 0
        for candidate in await self.repository.list_active():
            run = await self.repository.get_run(candidate.suite_run_id, for_update=True)
            if run is None or run.status in SUITE_TERMINAL_STATUSES:
                continue
            items = await self.repository.list_items(run.suite_run_id)
            active = [item for item in items if item.status in {"queued", "running"}]
            if active:
                children = await self.runs.list_by_ids(
                    [item.child_run_id for item in active if item.child_run_id]
                )
                terminal = next(
                    (
                        item
                        for item in active
                        if item.child_run_id in children
                        and children[item.child_run_id].status in PERF_RUN_TERMINAL_STATUSES
                    ),
                    None,
                )
                if terminal is not None:
                    await self.on_child_completed(terminal.child_run_id)
                    repaired += 1
                continue
            pending = [item for item in items if item.status == "pending"]
            if run.status == PerfRunStatus.STOPPING.value:
                await self._skip_unstarted(items)
                self._finish(
                    run,
                    items,
                    status=PerfRunStatus.CANCELED.value,
                    outcome="stopped",
                )
                await self.repository.commit()
                repaired += 1
            elif pending:
                await self.start_next(run.suite_run_id)
                repaired += 1
            else:
                self._finish(
                    run,
                    items,
                    status=PerfRunStatus.COMPLETED.value,
                    outcome="inconclusive",
                )
                await self.repository.commit()
                repaired += 1
        return repaired

    async def list_runs(
        self,
        user_id: str,
        project_id: str,
        *,
        suite_id: str = "",
        status: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        await require_project_id(self.repository.session, user_id, project_id, action="read")
        if status and status not in {item.value for item in PerfRunStatus}:
            raise ErrBadRequest()
        rows, total = await self.repository.list_by_project(
            project_id,
            suite_id=suite_id,
            status=status,
            page=max(page, 1),
            page_size=min(max(page_size, 1), 100),
        )
        return {"total": total, "items": [self._summary(row) for row in rows]}

    async def get(self, user_id: str, suite_run_id: str) -> dict[str, Any]:
        return await self._detail(await self._accessible_run(user_id, suite_run_id, action="read"))

    async def stop(self, user_id: str, suite_run_id: str) -> dict[str, Any]:
        run = await self.repository.get_run(suite_run_id, for_update=True)
        if run is None:
            raise ErrNotFound()
        await require_project_id(self.repository.session, user_id, run.project_id, action="execute")
        if run.trigger_user_id != user_id:
            raise ErrForbidden()
        if run.status in SUITE_TERMINAL_STATUSES:
            return {"status": run.status}
        run.status = PerfRunStatus.STOPPING.value
        items = await self.repository.list_items(suite_run_id)
        current = next((item for item in items if item.status in {"queued", "running"}), None)
        if current is not None:
            child = await self.runs.get_run(current.child_run_id, for_update=True)
            if child is not None and await halt_perf_run(self.repository.session, child):
                current.status = "canceled"
                current.outcome = "stopped"
                current.finished_at = child.finished_at
        await self._skip_unstarted(items)
        if current is None or current.status == "canceled":
            self._finish(
                run,
                items,
                status=PerfRunStatus.CANCELED.value,
                outcome="stopped",
            )
        await self.repository.commit()
        return {"status": run.status}

    async def stop_child(self, user_id: str, child_run_id: str) -> dict[str, Any] | None:
        """Stop the whole serial suite from one of its child runs.

        Returns None when no suite item owns the run.
        """
        item = await self.repository.get_item_by_child_run(child_run_id)
        if item is None:
            return None
        await self.stop(user_id, item.suite_run_id)
        child = await self.runs.get_run(child_run_id)
        return {"status": child.status if child is not None else PerfRunStatus.CANCELED.value}


def suite_run_service(session) -> PerfSuiteRunService:
    return PerfSuiteRunService(
        PerfSuiteRunRepository(session),
        suites=PerfSuiteRepository(session),
        cases=PerfCaseRepository(session),
        runs=PerfRunRepository(session),
    )


async def on_child_started_after_commit(session, child_run_id: str) -> None:
    await suite_run_service(session).on_child_started(child_run_id)


async def on_child_completed_after_commit(session, child_run_id: str) -> None:
    await suite_run_service(session).on_child_completed(child_run_id)
