from __future__ import annotations

import asyncio
import signal
from contextlib import suppress

import pytest

from test_worker import __main__ as worker_main
from test_worker.contracts.types import (
    UiCaseRunSnapshot,
    UiCaseSnapshot,
    UiWorkerTask,
    UiWorkerTaskSnapshotResponse,
    WorkerConfig,
)
from test_worker.control_plane.client import (
    ControlPlaneRequestError,
    ExecutionLeaseLost,
)
from test_worker.poller.task_poller import TaskLease, TaskPoller


def test_shutdown_signal_cancels_worker_and_runs_cleanup(monkeypatch) -> None:
    registered_handlers: dict[signal.Signals, tuple] = {}
    cleanup_completed = asyncio.Event()
    worker_started = asyncio.Event()

    async def fake_main() -> None:
        worker_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup_completed.set()

    async def run_scenario() -> None:
        loop = asyncio.get_running_loop()

        def capture_handler(handled_signal, callback, *args) -> None:
            registered_handlers[handled_signal] = (callback, args)

        monkeypatch.setattr(loop, "add_signal_handler", capture_handler)
        monkeypatch.setattr(loop, "remove_signal_handler", lambda handled_signal: True)
        monkeypatch.setattr(worker_main, "_main", fake_main)

        shutdown_task = asyncio.create_task(worker_main._run_with_shutdown_signals())
        await worker_started.wait()

        callback, args = registered_handlers[signal.SIGTERM]
        callback(*args)
        await shutdown_task

    asyncio.run(run_scenario())

    assert cleanup_completed.is_set()


def test_canceling_claimed_task_reports_shutdown_canceled() -> None:
    class FakeControlPlaneClient:
        def __init__(self) -> None:
            self.completed = []

        def report_task_started(self, task_id, payload) -> None:
            return None

        def get_task_snapshot(self, task_id) -> UiWorkerTaskSnapshotResponse:
            return UiWorkerTaskSnapshotResponse(
                task_type="case_debug",
                case_run=UiCaseRunSnapshot(
                    task_id=task_id,
                    run_id="run-1",
                    case=UiCaseSnapshot(case_id="case-1", name="Case"),
                ),
            )

        def report_task_completed(self, task_id, result) -> None:
            self.completed.append((task_id, result))

    class BlockingCaseRunner:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.cleaned_up = asyncio.Event()

        async def run(self, snapshot):
            self.started.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.cleaned_up.set()

    async def run_scenario() -> tuple[FakeControlPlaneClient, BlockingCaseRunner]:
        config = WorkerConfig(
            mode="poll",
            worker_id="worker-1",
            control_plane_base_url="http://control-plane",
            worker_token="token",
            poll_interval_ms=100,
            request_timeout_ms=1000,
            heartbeat_interval_ms=1000,
            artifacts_root_dir="artifacts",
            trace_enabled=False,
            snapshot_file="",
        )
        client = FakeControlPlaneClient()
        runner = BlockingCaseRunner()
        poller = TaskPoller(config, client, runner, object())  # type: ignore[arg-type]
        claimed_task = UiWorkerTask(
            task_id="task-1",
            task_type="case_debug",
            run_id="run-1",
            case_id="case-1",
        )

        execution = asyncio.create_task(poller._handle_task(claimed_task))
        await runner.started.wait()
        execution.cancel()
        with pytest.raises(asyncio.CancelledError):
            await execution
        return client, runner

    client, runner = asyncio.run(run_scenario())

    assert runner.cleaned_up.is_set()
    assert len(client.completed) == 1
    _, result = client.completed[0]
    assert result.status == "canceled"
    assert result.error_message == "worker shutting down"


def test_control_plane_disconnect_stops_operation_after_lease_window() -> None:
    class DisconnectedClient:
        def report_task_heartbeat(self, *args):
            raise ConnectionError("control plane unreachable")

        def task_stop_requested(self, *args):
            return False

    async def run() -> tuple[list[str], TaskLease]:
        poller = TaskPoller(
            SimpleConfig(heartbeat_interval_ms=1),
            DisconnectedClient(),
            None,
            None,
        )
        lease = TaskLease(0.1)
        effects: list[str] = []

        async def operation():
            try:
                await asyncio.sleep(0.5)
                effects.append("side-effect")
            finally:
                effects.append("canceled")

        heartbeat = asyncio.create_task(poller._heartbeat_loop("task-1", lease))
        try:
            with pytest.raises(ExecutionLeaseLost):
                await asyncio.wait_for(
                    poller._run_until_stopped(
                        "api", "task-1", operation(), lease=lease
                    ),
                    timeout=1,
                )
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
        return effects, lease

    effects, lease = asyncio.run(run())

    assert effects == ["canceled"]
    assert lease.lost


def test_heartbeat_rejection_expires_local_lease() -> None:
    class RejectedClient:
        def report_task_heartbeat(self, *args):
            raise ControlPlaneRequestError("POST", "/heartbeat", 403)

    async def run() -> TaskLease:
        lease = TaskLease(5)
        poller = TaskPoller(
            SimpleConfig(heartbeat_interval_ms=1),
            RejectedClient(),
            None,
            None,
        )
        await asyncio.wait_for(poller._heartbeat_loop("task-1", lease), timeout=1)
        return lease

    lease = asyncio.run(run())

    assert lease.lost


class SimpleConfig:
    def __init__(self, *, heartbeat_interval_ms: int) -> None:
        self.worker_id = "worker-1"
        self.heartbeat_interval_ms = heartbeat_interval_ms
