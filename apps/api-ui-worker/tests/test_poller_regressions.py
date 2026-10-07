import asyncio
from types import SimpleNamespace

from test_worker.poller.task_poller import TaskPoller


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
        task = asyncio.create_task(poller._heartbeat_loop("fixture"))
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
