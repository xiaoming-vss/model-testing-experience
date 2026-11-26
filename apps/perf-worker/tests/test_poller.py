from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from support import base_spec_dict, make_settings

from testing_agent_perf_worker.contracts.result import (
    RunOutcome,
    RunResult,
    RunStatus,
)
from testing_agent_perf_worker.contracts.spec import RunSpec
from testing_agent_perf_worker.contracts.worker import (
    ClaimResponse,
    ControlResponse,
    DataFileRef,
    HeartbeatResponse,
    SnapshotResponse,
)
from testing_agent_perf_worker.core.errors import (
    ControlPlaneError,
    DataFileError,
    ExecutionError,
    LeaseLostError,
)
from testing_agent_perf_worker.runner.k6 import K6Execution
from testing_agent_perf_worker.runner.workspace import Workspace
from testing_agent_perf_worker.worker import poller as poller_module
from testing_agent_perf_worker.worker.lease import ExecutionWindow
from testing_agent_perf_worker.worker.poller import PerfPoller, StopReason

_CLAIM = ClaimResponse(
    task_id="task-1",
    task_type="perf_run",
    run_id="run-001",
    status="claimed",
    lease_seconds=60,
)


def _snapshot(*, data_files: list[DataFileRef] | None = None) -> SnapshotResponse:
    return SnapshotResponse(
        task_id="task-1",
        run_id="run-001",
        case_name="case",
        run_spec=RunSpec.model_validate(base_spec_dict()),
        data_files=data_files or [],
        lease_seconds=60,
    )


def _execution(*, stopped: bool = False, exit_code: int = 0) -> K6Execution:
    now = datetime.now(UTC)
    summary: dict[str, Any] = {
        "metrics": {"http_reqs": {"type": "counter", "values": {"count": 1}}}
    }
    return K6Execution(
        exit_code=exit_code,
        started_at=now,
        finished_at=now,
        duration_ms=5,
        summary=summary,
        summary_missing=False,
        stopped=stopped,
        timed_out=False,
        k6_version="2.3.0",
        log_tail="",
        log_truncated=False,
        error_message="",
    )


class FakeClient:
    def __init__(
        self,
        *,
        snapshot: SnapshotResponse | None = None,
        control: ControlResponse | None = None,
        download_error: Exception | None = None,
        on_complete: Any = None,
    ) -> None:
        self._snapshot = snapshot or _snapshot()
        self._control = control or ControlResponse(stop_requested=False)
        self._download_error = download_error
        self._on_complete = on_complete
        self.completions: list[dict[str, Any]] = []
        self.started_calls: list[str] = []
        self.heartbeats = 0
        self.closed = False

    async def claim(self, worker_id: str) -> ClaimResponse:
        return _CLAIM

    async def snapshot(self, task_id: str, worker_id: str) -> SnapshotResponse:
        return self._snapshot

    async def started(self, task_id: str, worker_id: str, started_at: str) -> None:
        self.started_calls.append(started_at)

    async def heartbeat(self, task_id: str, worker_id: str) -> HeartbeatResponse:
        self.heartbeats += 1
        return HeartbeatResponse(stop_requested=False, lease_seconds=60)

    async def control(self, task_id: str, worker_id: str) -> ControlResponse:
        return self._control

    async def complete(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.completions.append(payload)
        if self._on_complete is not None:
            self._on_complete()
        return {"status": "success"}

    async def download_data_file(
        self,
        task_id: str,
        file: DataFileRef,
        worker_id: str,
        destination: Path,
        *,
        max_bytes: int,
    ) -> None:
        if self._download_error is not None:
            raise self._download_error
        destination.write_bytes(b"u1,p1\n")

    async def close(self) -> None:
        self.closed = True


class FakeRunner:
    executions: list[K6Execution] = []

    def __init__(self, settings: Any) -> None:
        self.settings = settings

    async def check_version(self) -> str:
        return "2.3.0"

    async def run(self, compiled: Any, workspace: Any, stop_event: Any = None) -> K6Execution:
        return self.executions.pop(0)


def _settings(tmp_path: Path):
    settings = make_settings(tmp_path, tmp_path / "unused-k6")
    settings.worker.health_file = str(tmp_path / "runtime" / "health.json")
    return settings


@pytest.mark.asyncio
async def test_execute_claims_runs_and_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    FakeRunner.executions = [_execution()]
    monkeypatch.setattr(poller_module, "K6Runner", FakeRunner)
    client = FakeClient()
    poller = PerfPoller(_settings(tmp_path), client=client)  # type: ignore[arg-type]

    await poller._execute(_CLAIM)

    assert len(client.completions) == 1
    payload = client.completions[0]
    assert payload["workerId"] == poller.worker_id
    assert payload["runId"] == "run-001"
    assert payload["status"] == "completed"
    assert payload["outcome"] == "passed"
    assert len(client.started_calls) == 1

    workspace = Path(poller.settings.runner.workspace_root) / "run-001"
    assert (workspace / "inputs" / "spec.json").is_file()
    assert (workspace / "plan.json").is_file()
    assert (workspace / "main.js").is_file()
    assert (workspace / "result.json").is_file()


@pytest.mark.asyncio
async def test_run_executes_one_task_then_shuts_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    FakeRunner.executions = [_execution()]
    monkeypatch.setattr(poller_module, "K6Runner", FakeRunner)
    holder: dict[str, PerfPoller] = {}

    def shutdown_after_complete() -> None:
        holder["poller"].shutdown_event.set()

    client = FakeClient(on_complete=shutdown_after_complete)
    poller = PerfPoller(_settings(tmp_path), client=client)  # type: ignore[arg-type]
    holder["poller"] = poller

    await asyncio.wait_for(poller.run(), timeout=5)

    assert len(client.completions) == 1
    assert client.closed is True


@pytest.mark.asyncio
async def test_data_file_failure_is_reported_without_running_k6(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    called = False

    class ForbiddenRunner:
        def __init__(self, settings: Any) -> None:
            self.settings = settings

        async def run(self, *_args: Any, **_kwargs: Any) -> K6Execution:
            raise AssertionError("k6 must not run after a preflight failure")

    def mark_called() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(poller_module, "K6Runner", ForbiddenRunner)
    file = DataFileRef(
        file_id="file-1",
        filename="users.csv",
        size=6,
        sha256="a" * 64,
    )
    client = FakeClient(
        snapshot=_snapshot(data_files=[file]),
        download_error=DataFileError("校验失败"),
        on_complete=mark_called,
    )
    poller = PerfPoller(_settings(tmp_path), client=client)  # type: ignore[arg-type]

    await poller._execute(_CLAIM)

    assert called is True
    payload = client.completions[0]
    assert payload["status"] == "failed"
    assert payload["outcome"] == "execution_error"
    assert "校验失败" in payload["errorMessage"]


@pytest.mark.asyncio
async def test_control_stop_before_execution_reports_canceled(tmp_path: Path):
    client = FakeClient(control=ControlResponse(stop_requested=True))
    poller = PerfPoller(_settings(tmp_path), client=client)  # type: ignore[arg-type]

    await poller._execute(_CLAIM)

    assert client.started_calls == []
    payload = client.completions[0]
    assert payload["status"] == "canceled"
    assert payload["outcome"] == "stopped"
    assert "用户已停止" in payload["errorMessage"]


@pytest.mark.asyncio
async def test_heartbeat_lease_rejection_stops_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    async def no_sleep(_seconds: float) -> None:
        return None

    class RejectingClient(FakeClient):
        async def heartbeat(self, task_id: str, worker_id: str) -> HeartbeatResponse:
            raise LeaseLostError("租约失效", 403)

    monkeypatch.setattr(poller_module.asyncio, "sleep", no_sleep)
    settings = _settings(tmp_path)
    settings.worker.heartbeat_interval_seconds = 1
    poller = PerfPoller(settings, client=RejectingClient())  # type: ignore[arg-type]
    window = ExecutionWindow.start(60, 5)

    await poller._heartbeat("task-1", window)

    assert window.lost is True
    assert poller.stop_reason is StopReason.LEASE_LOST
    assert poller.stop_event.is_set()


def test_stop_reason_overrides_completed_result():
    poller = object.__new__(PerfPoller)
    poller.stop_reason = StopReason.USER
    result = RunResult(
        run_id="run-001",
        status=RunStatus.COMPLETED,
        outcome=RunOutcome.PASSED,
        exit_code=0,
        started_at="2026-11-16T00:00:00+00:00",
        finished_at="2026-11-16T00:00:01+00:00",
        duration_ms=1000,
    )

    canceled = poller._apply_stop_reason(result, _execution(stopped=True))
    assert canceled.status is RunStatus.CANCELED
    assert canceled.outcome is RunOutcome.STOPPED

    poller.stop_reason = StopReason.SHUTDOWN
    stopped = poller._apply_stop_reason(result, _execution(stopped=True))
    assert stopped.status is RunStatus.STOPPED
    assert stopped.outcome is RunOutcome.STOPPED
    assert "关闭" in stopped.error_message


@pytest.mark.asyncio
async def test_completion_retries_until_control_plane_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    FakeRunner.executions = [_execution()]
    monkeypatch.setattr(poller_module, "K6Runner", FakeRunner)

    class FlakyCompleteClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.attempts = 0

        async def complete(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
            self.attempts += 1
            self.completions.append(payload)
            if self.attempts <= 2:
                raise ControlPlaneError("控制面暂时不可用", 503)
            return {"status": "success"}

    client = FlakyCompleteClient()
    poller = PerfPoller(_settings(tmp_path), client=client)  # type: ignore[arg-type]

    await poller._execute(_CLAIM)

    assert client.attempts == 3
    assert len(client.completions) == 3
    assert client.completions[0] == client.completions[1] == client.completions[2]
    workspace = Path(poller.settings.runner.workspace_root) / "run-001"
    assert json.loads((workspace / "result.json").read_text(encoding="utf-8"))["status"] == (
        "completed"
    )


@pytest.mark.asyncio
async def test_completion_stops_at_lease_deadline_and_keeps_result(tmp_path: Path):
    class UnavailableClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.attempts = 0

        async def complete(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
            self.attempts += 1
            raise ControlPlaneError("控制面暂时不可用", 503)

    client = UnavailableClient()
    poller = PerfPoller(_settings(tmp_path), client=client)  # type: ignore[arg-type]
    workspace = Workspace.create(tmp_path / "workspaces", "run-001")
    window = ExecutionWindow.start(
        1,
        0,
        started_monotonic=time.monotonic() - 0.7,
    )
    result = poller_module._special_result(
        "run-001",
        RunStatus.STOPPED,
        RunOutcome.STOPPED,
        datetime.now(UTC).isoformat(),
        "控制面执行租约已失效，执行已停止",
    )

    await poller._report(_CLAIM, result, workspace, window)

    assert client.attempts >= 2
    assert client.attempts < 5
    saved = json.loads(workspace.result_path.read_text(encoding="utf-8"))
    assert saved["status"] == "stopped"


@pytest.mark.asyncio
async def test_shutdown_before_execution_reports_stopped(tmp_path: Path):
    client = FakeClient()
    poller = PerfPoller(_settings(tmp_path), client=client)  # type: ignore[arg-type]
    poller.request_shutdown()

    await poller._execute(_CLAIM)

    assert client.started_calls == []
    assert client.completions[0]["status"] == "stopped"
    assert "关闭" in client.completions[0]["errorMessage"]


@pytest.mark.asyncio
async def test_shutdown_during_preflight_reports_stopped(tmp_path: Path):
    holder: dict[str, PerfPoller] = {}

    class ShutdownOnControlClient(FakeClient):
        async def control(self, task_id: str, worker_id: str) -> ControlResponse:
            holder["poller"].request_shutdown()
            return ControlResponse(stop_requested=False)

    client = ShutdownOnControlClient()
    poller = PerfPoller(_settings(tmp_path), client=client)  # type: ignore[arg-type]
    holder["poller"] = poller

    await poller._execute(_CLAIM)

    assert client.started_calls == []
    assert client.completions[0]["status"] == "stopped"
    assert "关闭" in client.completions[0]["errorMessage"]


@pytest.mark.asyncio
async def test_shutdown_during_k6_run_reports_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    started = asyncio.Event()

    class WaitingRunner:
        def __init__(self, settings: Any) -> None:
            self.settings = settings

        async def run(self, compiled: Any, workspace: Any, stop_event: Any = None):
            started.set()
            await stop_event.wait()
            return _execution(stopped=True)

    monkeypatch.setattr(poller_module, "K6Runner", WaitingRunner)
    client = FakeClient()
    poller = PerfPoller(_settings(tmp_path), client=client)  # type: ignore[arg-type]

    execution = asyncio.create_task(poller._execute(_CLAIM))
    await started.wait()
    poller.request_shutdown()
    await execution

    assert client.completions[0]["status"] == "stopped"
    assert "关闭" in client.completions[0]["errorMessage"]


@pytest.mark.asyncio
async def test_startup_rejects_mismatched_k6_before_claiming(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    class RejectingRunner:
        def __init__(self, settings: Any) -> None:
            self.settings = settings

        async def check_version(self) -> str:
            raise ExecutionError("k6 版本不匹配: 期望 2.3.0，实际 2.2.0")

    monkeypatch.setattr(poller_module, "K6Runner", RejectingRunner)
    client = FakeClient()
    poller = PerfPoller(_settings(tmp_path), client=client)  # type: ignore[arg-type]

    with pytest.raises(ExecutionError, match="k6 版本不匹配"):
        await poller.run()

    assert client.completions == []
    assert client.closed is True


@pytest.mark.asyncio
async def test_shutdown_grace_cancels_an_active_run_that_does_not_stop(tmp_path: Path):
    settings = _settings(tmp_path)
    settings.worker.shutdown_grace_seconds = 1
    poller = PerfPoller(settings, client=FakeClient())  # type: ignore[arg-type]
    poller._active = True
    execution = asyncio.create_task(asyncio.sleep(30))
    poller._execution_task = execution
    started = time.monotonic()

    poller.request_shutdown()

    with pytest.raises(asyncio.CancelledError):
        await execution
    assert time.monotonic() - started < 3
    assert poller._shutdown_watchdog is not None
    await asyncio.gather(poller._shutdown_watchdog, return_exceptions=True)


@pytest.mark.asyncio
async def test_snapshot_lease_rejection_does_not_synthesize_a_result(tmp_path: Path):
    class RejectingSnapshotClient(FakeClient):
        async def snapshot(self, task_id: str, worker_id: str) -> SnapshotResponse:
            raise LeaseLostError("控制面已拒绝当前执行租约", 409)

    client = RejectingSnapshotClient()
    poller = PerfPoller(_settings(tmp_path), client=client)  # type: ignore[arg-type]

    await poller._execute(_CLAIM)

    # The control plane ends the attempt by lease; a failed result would only be rejected.
    assert client.completions == []
    assert client.started_calls == []
    assert poller.stop_reason is StopReason.LEASE_LOST


@pytest.mark.asyncio
async def test_snapshot_control_plane_failure_is_reported_as_a_failure(tmp_path: Path):
    class UnavailableSnapshotClient(FakeClient):
        async def snapshot(self, task_id: str, worker_id: str) -> SnapshotResponse:
            raise ControlPlaneError("控制面暂时不可用", 503)

    client = UnavailableSnapshotClient()
    poller = PerfPoller(_settings(tmp_path), client=client)  # type: ignore[arg-type]

    await poller._execute(_CLAIM)

    payload = client.completions[0]
    assert payload["status"] == "failed"
    assert payload["outcome"] == "execution_error"
    assert "获取运行快照失败" in payload["errorMessage"]


@pytest.mark.asyncio
async def test_snapshot_protocol_violation_is_reported_instead_of_crashing(tmp_path: Path):
    class MalformedSnapshotClient(FakeClient):
        async def snapshot(self, task_id: str, worker_id: str) -> SnapshotResponse:
            raise ValidationError.from_exception_data(
                "SnapshotResponse", [{"type": "missing", "loc": ("runId",), "input": {}}]
            )

    client = MalformedSnapshotClient()
    poller = PerfPoller(_settings(tmp_path), client=client)  # type: ignore[arg-type]

    # This used to escape the poll loop and take the whole worker down.
    await poller._execute(_CLAIM)

    payload = client.completions[0]
    assert payload["status"] == "failed"
    assert payload["errorMessage"] == "运行快照不符合协议"


@pytest.mark.asyncio
async def test_poll_loop_removes_the_health_file_on_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    FakeRunner.executions = [_execution()]
    monkeypatch.setattr(poller_module, "K6Runner", FakeRunner)
    settings = _settings(tmp_path)
    health_path = Path(settings.worker.health_file)
    holder: dict[str, PerfPoller] = {}

    def shutdown_after_complete() -> None:
        assert health_path.is_file()
        holder["poller"].shutdown_event.set()

    client = FakeClient(on_complete=shutdown_after_complete)
    poller = PerfPoller(settings, client=client)  # type: ignore[arg-type]
    holder["poller"] = poller

    await asyncio.wait_for(poller.run(), timeout=5)

    assert len(client.completions) == 1
    # A leftover file with a dead PID is unreliable once the PID is reused.
    assert not health_path.exists()


@pytest.mark.asyncio
async def test_rejected_claim_and_completion_log_their_status_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    FakeRunner.executions = [_execution()]
    monkeypatch.setattr(poller_module, "K6Runner", FakeRunner)
    holder: dict[str, PerfPoller] = {}

    class RejectingClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.claims = 0

        async def claim(self, worker_id: str) -> ClaimResponse:
            self.claims += 1
            if self.claims > 1:
                holder["poller"].shutdown_event.set()
            raise LeaseLostError("控制面已拒绝当前执行租约", 401)

        async def complete(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
            self.completions.append(payload)
            raise LeaseLostError("控制面已拒绝当前执行租约", 400)

    client = RejectingClient()
    poller = PerfPoller(_settings(tmp_path), client=client)  # type: ignore[arg-type]
    holder["poller"] = poller

    with caplog.at_level(logging.WARNING, logger="testing_agent_perf_worker"):
        await poller._execute(_CLAIM)
        await asyncio.wait_for(poller.run(), timeout=5)

    messages = [record.getMessage() for record in caplog.records]
    # A misconfigured token or an oversized payload must be tellable apart in the log.
    assert any(message == "completion rejected task_id=task-1 status=400" for message in messages)
    assert sum(message == "claim rejected status=401" for message in messages) == 2
