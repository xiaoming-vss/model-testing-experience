from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
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
from testing_agent_perf_worker.core.errors import DataFileError, LeaseLostError
from testing_agent_perf_worker.runner.k6 import K6Execution
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
