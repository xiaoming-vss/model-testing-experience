import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from test_worker.contracts.types import UiCaseRunResult, UiWorkerTask
from test_worker.control_plane.client import (
    ControlPlaneRequestError,
    ExecutionLeaseLost,
)
from test_worker.core.reporting import ReportDeliveryError
from test_worker.poller import task_poller
from test_worker.poller.task_poller import TaskLease, TaskPoller
from test_worker.ui.step_progress import report_steps


@pytest.mark.parametrize("domain", ["api", "ui"])
def test_explicitly_rejected_lease_cancels_active_execution(domain):
    canceled = []

    class Client:
        def task_stop_requested(self, *_args):
            raise ControlPlaneRequestError("GET", "/task", 400)

    async def run():
        async def operation():
            try:
                await asyncio.Event().wait()
            finally:
                canceled.append(True)

        poller = TaskPoller(SimpleNamespace(redis_url=""), Client(), None, None)
        with pytest.raises(ExecutionLeaseLost):
            await asyncio.wait_for(
                poller._run_until_stopped(domain, "task", operation()), 1
            )

    asyncio.run(run())
    assert canceled == [True]


@pytest.mark.parametrize(
    "status, rejected",
    [
        (400, False),
        (401, True),
        (403, True),
        (409, True),
        (422, False),
        (503, False),
    ],
)
def test_step_progress_stops_only_on_explicit_control_plane_rejection(status, rejected):
    class Client:
        def report_ui_steps(self, *_args):
            raise ControlPlaneRequestError("GET", "/task", status)

    async def run():
        if rejected:
            with pytest.raises(ExecutionLeaseLost):
                await report_steps(Client(), "task", "item", [])
        else:
            await report_steps(Client(), "task", "item", [])

    asyncio.run(run())


def test_api_queue_is_not_starved_by_continuous_ui_backlog():
    counts = {"ui": 0, "api_claims": 0, "api": 0}

    class Client:
        def claim_task(self):
            return SimpleNamespace(task_id="fixture-ui")

        def claim_api_task(self):
            counts["api_claims"] += 1
            return SimpleNamespace(task_id="fixture-api")

    class Poller(TaskPoller):
        async def _handle_task(self, task):
            counts["ui"] += 1
            if counts["ui"] == 6:
                raise asyncio.CancelledError()

        async def _handle_api_task(self, task):
            counts["api"] += 1

    async def run():
        poller = Poller(
            SimpleNamespace(worker_id="fixture", mode="poll", poll_interval_ms=1),
            Client(),
            None,
            None,
        )
        try:
            await poller.start()
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
    assert counts == {"ui": 6, "api_claims": 5, "api": 5}, (
        "Continuously pending UI and API queues must both execute tasks"
    )


def test_slow_heartbeat_http_does_not_block_async_browser_work():
    import threading

    started = threading.Event()
    release = threading.Event()
    completed = threading.Event()

    class Client:
        def report_task_heartbeat(self, *args):
            started.set()
            release.wait(timeout=2)
            completed.set()

    async def run():
        poller = TaskPoller(
            SimpleNamespace(worker_id="fixture", heartbeat_interval_ms=1),
            Client(),
            None,
            None,
        )
        task = asyncio.create_task(poller._heartbeat_loop("fixture", TaskLease(5)))
        try:
            assert await asyncio.wait_for(
                asyncio.to_thread(started.wait, 1), timeout=1.5
            )
            # A browser timer must run while the HTTP request is still blocked.
            await asyncio.sleep(0.005)
            assert not completed.is_set()
        finally:
            release.set()
            task.cancel()
            await task

    asyncio.run(run())


def test_api_snapshot_logging_does_not_disclose_executor_credentials():
    import json
    from unittest.mock import patch

    from test_worker.poller import task_poller

    marker = "CREDENTIAL_AUDIT_MARKER"
    events = []

    class Client:
        def report_api_task_started(self, *args):
            pass

        def get_api_task_snapshot(self, *args):
            return {
                "caseRun": {
                    "request": {"headers": {"Authorization": marker}},
                    "runtimeVars": {"token": marker},
                }
            }

        def report_api_task_completed(self, *args):
            pass

    class Runner:
        async def run(self, snapshot):
            assert snapshot["request"]["headers"]["Authorization"] == marker
            return {"status": "success", "success": True}

    async def run():
        poller = TaskPoller(
            SimpleNamespace(worker_id="fixture", heartbeat_interval_ms=10000),
            Client(),
            None,
            None,
        )
        poller._api_case_runner = Runner()
        await poller._handle_api_task(
            {"taskId": "fixture", "taskType": "api_case_debug", "runId": "fixture-run"}
        )

    with patch.object(
        task_poller.logger,
        "info",
        side_effect=lambda message, meta: events.append((message, meta)),
    ):
        asyncio.run(run())
    assert any(message == "api task completed" for message, _ in events)
    assert marker not in json.dumps(events), (
        "The full API executor snapshot is logged without secret redaction"
    )


def test_ui_snapshot_logging_does_not_disclose_step_credentials():
    import json
    from unittest.mock import patch

    from test_worker.contracts.types import (
        UiCaseRunSnapshot,
        UiCaseSnapshot,
        UiWorkerTask,
        UiWorkerTaskSnapshotResponse,
    )
    from test_worker.poller import task_poller

    events = []
    marker = "UI_CREDENTIAL_MARKER"

    class Client:
        def report_task_started(self, *args):
            pass

        def get_task_snapshot(self, task_id):
            return UiWorkerTaskSnapshotResponse(
                task_type="case_debug",
                case_run=UiCaseRunSnapshot(
                    task_id=task_id,
                    run_id="run",
                    case=UiCaseSnapshot(
                        case_id="case",
                        name="case",
                        steps_json=[{"action": "fill", "value": marker}],
                    ),
                ),
            )

        def report_task_completed(self, *args):
            pass

    class Runner:
        async def run(self, snapshot):
            assert marker in snapshot.case.steps_json[0]["value"]
            return SimpleNamespace(status="success", success=True)

    async def run():
        poller = TaskPoller(
            SimpleNamespace(worker_id="fixture", heartbeat_interval_ms=10000),
            Client(),
            Runner(),
            None,
        )
        await poller._handle_task(
            UiWorkerTask(task_id="fixture", task_type="case_debug", run_id="run")
        )

    with patch.object(
        task_poller.logger,
        "info",
        side_effect=lambda message, meta: events.append((message, meta)),
    ):
        asyncio.run(run())
    assert any(message == "task completed" for message, _ in events)
    assert marker not in json.dumps(events)


def _ui_success_result() -> UiCaseRunResult:
    return UiCaseRunResult(
        task_id="task-1",
        run_id="run-1",
        case_id="case-1",
        status="success",
        success=True,
        started_at="2026-11-19T00:00:00+00:00",
        finished_at="2026-11-19T00:00:01+00:00",
        duration_ms=1000,
    )


@pytest.mark.parametrize("record_before_raise", [True, False])
def test_ui_completion_delivery_failure_is_not_execution_error(record_before_raise):
    completed = []
    events = []

    class Client:
        def report_task_started(self, *args):
            pass

        def get_task_snapshot(self, task_id):
            return SimpleNamespace(case_run=SimpleNamespace())

        def report_task_completed(self, task_id, result):
            if record_before_raise:
                completed.append(result)
            raise ControlPlaneRequestError(
                "POST", f"/internal/ui-worker/tasks/{task_id}/completed", 503
            )

    class Runner:
        async def run(self, snapshot):
            return _ui_success_result()

    async def run():
        poller = TaskPoller(
            SimpleNamespace(worker_id="fixture", heartbeat_interval_ms=10000),
            Client(),
            Runner(),
            None,
        )
        await poller._handle_task(
            UiWorkerTask(
                task_id="task-1",
                task_type="case_debug",
                run_id="run-1",
                case_id="case-1",
            )
        )

    with patch.object(
        task_poller.logger,
        "error",
        side_effect=lambda message, meta: events.append((message, meta)),
    ):
        asyncio.run(run())

    assert len(completed) == (1 if record_before_raise else 0)
    assert any(message == "ui task result delivery failed" for message, _ in events)
    assert not any(message == "task execution error" for message, _ in events)
    assert "SECRET-MARKER" not in json.dumps(events)


def test_api_upload_failure_is_not_execution_error():
    completed = []
    events = []

    class Client:
        def report_api_task_started(self, *args):
            pass

        def get_api_task_snapshot(self, task_id):
            return {"caseRun": {"caseId": "case-1"}}

        def report_api_task_completed(self, task_id, result):
            completed.append(result)
            raise ValueError("Artifact S3 upload failed: SECRET-MARKER path")

    class Runner:
        async def run(self, snapshot):
            return {"status": "success", "success": True}

    async def run():
        poller = TaskPoller(
            SimpleNamespace(worker_id="fixture", heartbeat_interval_ms=10000),
            Client(),
            None,
            None,
        )
        poller._api_case_runner = Runner()
        await poller._handle_api_task(
            {
                "taskId": "task-1",
                "taskType": "api_case_debug",
                "runId": "run-1",
            }
        )

    with patch.object(
        task_poller.logger,
        "error",
        side_effect=lambda message, meta: events.append((message, meta)),
    ):
        asyncio.run(run())

    assert len(completed) == 1
    assert completed[0]["success"] is True
    assert any(message == "api task result delivery failed" for message, _ in events)
    assert not any(message == "api task execution error" for message, _ in events)
    assert "SECRET-MARKER" not in json.dumps(events)


def test_execution_failure_still_reports_error_once():
    completed = []

    class Client:
        def report_task_started(self, *args):
            pass

        def get_task_snapshot(self, task_id):
            return SimpleNamespace(case_run=SimpleNamespace())

        def report_task_completed(self, task_id, result):
            completed.append(result)

    class Runner:
        async def run(self, snapshot):
            raise ValueError("assertion failed")

    async def run():
        poller = TaskPoller(
            SimpleNamespace(worker_id="fixture", heartbeat_interval_ms=10000),
            Client(),
            Runner(),
            None,
        )
        await poller._handle_task(
            UiWorkerTask(
                task_id="task-1",
                task_type="case_debug",
                run_id="run-1",
                case_id="case-1",
            )
        )

    asyncio.run(run())

    assert len(completed) == 1
    assert completed[0].status == "error"
    assert completed[0].success is False
    assert completed[0].error_message == "assertion failed"


def _collect_errors(events):
    return patch.object(
        task_poller.logger,
        "error",
        side_effect=lambda message, meta: events.append((message, meta)),
    )


def test_api_collection_item_delivery_failure_is_not_execution_error():
    executed = []
    completed = []
    events = []

    class Client:
        def report_api_task_started(self, *args):
            pass

        def report_api_task_heartbeat(self, *args):
            pass

        def get_api_task_snapshot(self, task_id):
            return {
                "collectionRun": {
                    "taskId": "task-1",
                    "runId": "run-1",
                    "items": [
                        {"itemId": "item-1", "caseRun": {"caseId": "case-1"}},
                        {"itemId": "item-2", "caseRun": {"caseId": "case-2"}},
                    ],
                }
            }

        def report_api_collection_item_started(self, task_id, item_id, payload):
            pass

        def report_api_collection_item_completed(self, task_id, item_id, payload):
            raise ControlPlaneRequestError(
                "POST",
                f"/internal/api-worker/tasks/{task_id}/collection-items/{item_id}/completed",
                503,
            )

        def report_api_task_completed(self, task_id, result):
            completed.append(result)

    class CaseRunner:
        async def run(self, case_run, runtime_vars):
            executed.append(case_run["caseId"])
            return {"status": "success", "success": True, "runtimeVarsJson": "{}"}

    async def run():
        poller = TaskPoller(
            SimpleNamespace(worker_id="fixture", heartbeat_interval_ms=10000),
            Client(),
            None,
            None,
        )
        poller._api_collection_runner._case_runner = CaseRunner()
        await poller._handle_api_task(
            {"taskId": "task-1", "taskType": "api_collection_run", "runId": "run-1"}
        )

    with _collect_errors(events):
        asyncio.run(run())

    # The first case succeeded but its result could not be delivered. That is a
    # delivery failure, not an execution error: no error result is synthesized and
    # later items are not executed on top of an undelivered one.
    assert executed == ["case-1"]
    assert completed == []
    deliveries = [
        meta for message, meta in events if message == "api task result delivery failed"
    ]
    assert [meta["statusCode"] for meta in deliveries] == [503]
    assert not any(message == "api task execution error" for message, _ in events)


def test_ui_suite_item_delivery_failure_is_not_turned_into_an_error_result(
    monkeypatch, tmp_path
):
    from test_worker.contracts.types import (
        UiCaseSnapshot,
        UiSuiteRunItemSnapshot,
        UiTestSuiteRunSnapshot,
    )
    from test_worker.core.reporting import ReportDeliveryError
    from test_worker.ui import suite_runner

    closed = []

    class Page:
        url = "https://app.example.test/"

    class Context:
        async def new_page(self):
            return Page()

        async def close(self):
            closed.append("context")

    class Browser:
        async def new_context(self, **_kwargs):
            return Context()

        async def close(self):
            closed.append("browser")

    async def launch(**_kwargs):
        return Browser()

    class Driver:
        chromium = SimpleNamespace(launch=launch)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    class Client:
        def report_suite_item_started(self, *args):
            pass

        def report_suite_item_completed(self, task_id, item_id, payload):
            raise ControlPlaneRequestError(
                "POST",
                f"/internal/ui-worker/tasks/{task_id}/suite-items/{item_id}/completed",
                503,
            )

    monkeypatch.setattr(suite_runner, "async_playwright", Driver)
    snapshot = UiTestSuiteRunSnapshot(
        task_id="task-1",
        run_id="run-1",
        items=[
            UiSuiteRunItemSnapshot(
                item_id="item-1",
                continue_on_failure=False,
                case=UiCaseSnapshot(case_id="case-1", name="用例一"),
            ),
            UiSuiteRunItemSnapshot(
                item_id="item-2",
                continue_on_failure=False,
                case=UiCaseSnapshot(case_id="case-2", name="用例二"),
            ),
        ],
    )
    config = SimpleNamespace(artifacts_root_dir=str(tmp_path), trace_enabled=False)
    runner = suite_runner.UiSuiteRunner(config, Client())

    # The item passed. A failed report used to come back as a suite `error` result.
    with pytest.raises(ReportDeliveryError) as caught:
        asyncio.run(runner.run(snapshot))

    assert caught.value.status_code == 503
    assert closed == ["context", "browser"]


def test_ui_suite_delivery_failure_is_not_reported_as_execution_error():
    completed = []
    events = []

    class Client:
        def report_task_started(self, *args):
            pass

        def get_task_snapshot(self, task_id):
            return SimpleNamespace(case_run=None, suite_run=SimpleNamespace())

        def report_task_completed(self, task_id, result):
            completed.append(result)

    class Runner:
        async def run(self, snapshot):
            raise ReportDeliveryError(
                "task-1",
                ControlPlaneRequestError(
                    "POST",
                    "/internal/ui-worker/tasks/task-1/suite-items/item-1/completed",
                    503,
                ),
            )

    async def run():
        poller = TaskPoller(
            SimpleNamespace(worker_id="fixture", heartbeat_interval_ms=10000),
            Client(),
            None,
            Runner(),
        )
        await poller._handle_task(
            UiWorkerTask(
                task_id="task-1",
                task_type="suite_run",
                run_id="run-1",
                case_id="case-1",
            )
        )

    with _collect_errors(events):
        asyncio.run(run())

    assert completed == []
    deliveries = [
        meta for message, meta in events if message == "ui task result delivery failed"
    ]
    assert [meta["statusCode"] for meta in deliveries] == [503]
    assert not any(message == "task execution error" for message, _ in events)
