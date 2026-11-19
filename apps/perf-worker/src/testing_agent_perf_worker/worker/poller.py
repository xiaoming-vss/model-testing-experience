"""Poll-mode lifecycle: claim, execute and report one performance run at a time."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import socket
import time
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from ..app import build_result
from ..compiler.compiler import CompiledPlan, compile_run_spec
from ..contracts.result import (
    RunnerInfo,
    RunOutcome,
    RunResult,
    RunStatus,
)
from ..contracts.worker import ClaimResponse, SnapshotResponse
from ..control_plane.client import ControlPlaneClient
from ..core.config import Settings
from ..core.errors import (
    CompileError,
    ControlPlaneError,
    DataFileError,
    ExecutionError,
    LeaseLostError,
    PerfWorkerError,
    SpecError,
)
from ..core.io import write_secure_text
from ..runner.k6 import K6Execution, K6Runner
from ..runner.workspace import Workspace
from ..worker.health import HealthFile
from ..worker.lease import ExecutionWindow

logger = logging.getLogger("testing_agent_perf_worker")

_MIB = 1024 * 1024


class StopReason(StrEnum):
    USER = "user"
    SHUTDOWN = "shutdown"
    LEASE_LOST = "lease_lost"


class PerfPoller:
    def __init__(
        self,
        settings: Settings,
        *,
        client: ControlPlaneClient | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or ControlPlaneClient(settings)
        self.worker_id = _worker_id(settings)
        self.health = HealthFile(
            Path(settings.worker.health_file),
            settings.worker.health_max_age_seconds,
        )
        self.shutdown_event = asyncio.Event()
        self.stop_event = asyncio.Event()
        self.stop_reason: StopReason | None = None
        self._active = False

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self.request_shutdown)
            except (NotImplementedError, RuntimeError):
                pass
        try:
            self.health.progress("polling")
            while not self.shutdown_event.is_set():
                try:
                    claim = await self.client.claim(self.worker_id)
                except LeaseLostError:
                    # A rejected token or server-side refusal must not spin.
                    await self._wait_or_shutdown(self.settings.worker.poll_interval_seconds)
                    continue
                except ControlPlaneError as exc:
                    logger.warning("claim failed status=%s", exc.status_code)
                    await self._wait_or_shutdown(self.settings.worker.poll_interval_seconds)
                    continue
                if claim is None:
                    self.health.progress("polling")
                    await self._wait_or_shutdown(self.settings.worker.poll_interval_seconds)
                    continue
                await self._execute(claim)
                self.health.progress("polling")
        finally:
            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    loop.remove_signal_handler(sig)
                except (NotImplementedError, RuntimeError):
                    pass
            self.health.progress("stopped")
            await self.client.close()

    def request_shutdown(self) -> None:
        self.shutdown_event.set()
        if self._active:
            self._request_stop(StopReason.SHUTDOWN)

    async def _wait_or_shutdown(self, timeout: float) -> None:
        if self.shutdown_event.is_set():
            return
        try:
            await asyncio.wait_for(self.shutdown_event.wait(), timeout=timeout)
        except TimeoutError:
            return

    async def _execute(self, claim: ClaimResponse) -> None:
        self.stop_event = asyncio.Event()
        self.stop_reason = None
        self._active = True
        started_iso = datetime.now(UTC).isoformat()
        started_monotonic = time.monotonic()
        window = ExecutionWindow.start(
            claim.lease_seconds,
            self.settings.worker.lease_margin_seconds,
            started_monotonic=started_monotonic,
        )
        if self.shutdown_event.is_set():
            await self._report(
                claim,
                _special_result(
                    claim.run_id,
                    RunStatus.CANCELED,
                    RunOutcome.STOPPED,
                    datetime.now(UTC).isoformat(),
                    "Worker 正在关闭，执行未启动",
                ),
                None,
                window,
            )
            self._active = False
            return
        workspace: Workspace | None = None
        heartbeat: asyncio.Task[None] | None = None
        snapshot: SnapshotResponse | None = None
        compiled: CompiledPlan | None = None
        execution: K6Execution | None = None
        preflight_error = ""
        try:
            try:
                snapshot = await self.client.snapshot(claim.task_id, self.worker_id)
            except (LeaseLostError, ControlPlaneError, PerfWorkerError) as exc:
                preflight_error = f"获取运行快照失败: {exc}"
                await self._report(
                    claim,
                    _special_result(
                        claim.run_id,
                        RunStatus.FAILED,
                        RunOutcome.EXECUTION_ERROR,
                        started_iso,
                        preflight_error,
                    ),
                    None,
                    window,
                )
                return
            if snapshot.run_id != claim.run_id:
                preflight_error = "控制面返回的运行快照与任务不一致"
                await self._report(
                    claim,
                    _special_result(
                        claim.run_id,
                        RunStatus.FAILED,
                        RunOutcome.EXECUTION_ERROR,
                        started_iso,
                        preflight_error,
                    ),
                    None,
                    window,
                )
                return
            try:
                control = await self.client.control(claim.task_id, self.worker_id)
            except LeaseLostError:
                self._request_stop(StopReason.LEASE_LOST, force=True)
                return
            except ControlPlaneError:
                control = None
            if control is not None and control.stop_requested:
                self._request_stop(StopReason.USER)
            if self.stop_event.is_set():
                await self._report(
                    claim,
                    _special_result(
                        claim.run_id,
                        RunStatus.CANCELED,
                        RunOutcome.STOPPED,
                        started_iso,
                        "用户已停止运行",
                    ),
                    None,
                    window,
                )
                return
            try:
                workspace = Workspace.create(
                    Path(self.settings.runner.workspace_root), claim.run_id
                )
            except ExecutionError as exc:
                await self._report(
                    claim,
                    _special_result(
                        claim.run_id,
                        RunStatus.FAILED,
                        RunOutcome.EXECUTION_ERROR,
                        started_iso,
                        str(exc),
                    ),
                    None,
                    window,
                )
                return

            self.health.progress("starting")
            try:
                await self.client.started(claim.task_id, self.worker_id, started_iso)
            except LeaseLostError:
                self._request_stop(StopReason.LEASE_LOST, force=True)
                return
            except ControlPlaneError as exc:
                preflight_error = f"上报运行开始失败: {exc}"
                await self._report(
                    claim,
                    _special_result(
                        claim.run_id,
                        RunStatus.FAILED,
                        RunOutcome.EXECUTION_ERROR,
                        started_iso,
                        preflight_error,
                    ),
                    workspace,
                    window,
                )
                return

            heartbeat = asyncio.create_task(
                self._heartbeat(claim.task_id, window),
                name=f"perf-heartbeat-{claim.task_id}",
            )
            if snapshot.run_spec.run_id != claim.run_id:
                preflight_error = "运行规格的 runId 与任务不一致"
            try:
                if not preflight_error:
                    write_secure_text(
                        workspace.inputs_dir / "spec.json",
                        json.dumps(
                            snapshot.run_spec.model_dump(by_alias=True, mode="json"),
                            ensure_ascii=False,
                            indent=2,
                        ),
                        overwrite=True,
                    )
                    await self._download_data_files(claim, snapshot, workspace)
                    compiled = compile_run_spec(
                        snapshot.run_spec,
                        workspace.inputs_dir,
                        workspace.root,
                        self.settings,
                    )
            except (DataFileError, SpecError, CompileError, ExecutionError) as exc:
                preflight_error = str(exc)
            if not preflight_error and not self.stop_event.is_set() and window.active():
                self.health.progress("running")
                if compiled is None:
                    preflight_error = "执行计划未生成"
                else:
                    execution = await K6Runner(self.settings).run(
                        compiled, workspace, self.stop_event
                    )
            if execution is not None and compiled is not None:
                result = build_result(snapshot.run_spec, compiled, execution)
                result = self._apply_stop_reason(result, execution)
            else:
                if self.stop_reason == StopReason.USER:
                    result = _special_result(
                        claim.run_id,
                        RunStatus.CANCELED,
                        RunOutcome.STOPPED,
                        started_iso,
                        "用户已停止运行",
                    )
                elif self.stop_reason == StopReason.SHUTDOWN:
                    result = _special_result(
                        claim.run_id,
                        RunStatus.STOPPED,
                        RunOutcome.STOPPED,
                        started_iso,
                        "Worker 正在关闭，执行已停止",
                    )
                elif self.stop_reason == StopReason.LEASE_LOST:
                    result = _special_result(
                        claim.run_id,
                        RunStatus.STOPPED,
                        RunOutcome.STOPPED,
                        started_iso,
                        "控制面执行租约已失效，执行已停止",
                    )
                else:
                    result = _special_result(
                        claim.run_id,
                        RunStatus.FAILED,
                        RunOutcome.EXECUTION_ERROR,
                        started_iso,
                        preflight_error or "执行未启动",
                    )
            await self._report(claim, result, workspace, window)
        finally:
            window.stop()
            if heartbeat is not None:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
            self._active = False

    async def _download_data_files(
        self,
        claim: ClaimResponse,
        snapshot: SnapshotResponse,
        workspace: Workspace,
    ) -> None:
        max_bytes = self.settings.runner.max_data_file_mb * _MIB
        total = 0
        for file in snapshot.data_files:
            total += file.size
            if total > max_bytes:
                raise DataFileError("数据文件总大小超过限制")
            await self.client.download_data_file(
                claim.task_id,
                file,
                self.worker_id,
                workspace.inputs_dir / file.filename,
                max_bytes=max_bytes,
            )

    async def _heartbeat(self, task_id: str, window: ExecutionWindow) -> None:
        interval = max(
            min(
                self.settings.worker.heartbeat_interval_seconds,
                window.lease_seconds / 3,
            ),
            1,
        )
        while True:
            await asyncio.sleep(interval)
            started = time.monotonic()
            try:
                response = await self.client.heartbeat(task_id, self.worker_id)
            except LeaseLostError:
                window.lose()
                self._request_stop(StopReason.LEASE_LOST, force=True)
                return
            except ControlPlaneError as exc:
                if not window.alive():
                    window.lose()
                    self._request_stop(StopReason.LEASE_LOST, force=True)
                    return
                logger.warning("heartbeat failed status=%s", exc.status_code)
                continue
            if not window.renew(response.lease_seconds, started_monotonic=started):
                self._request_stop(StopReason.LEASE_LOST, force=True)
                return
            if response.stop_requested:
                self._request_stop(StopReason.USER)
            self.health.progress("running")

    def _request_stop(self, reason: StopReason, *, force: bool = False) -> None:
        if self.stop_reason is None or force:
            self.stop_reason = reason
        self.stop_event.set()

    def _apply_stop_reason(self, result: RunResult, execution: K6Execution) -> RunResult:
        if not execution.stopped:
            return result
        if self.stop_reason == StopReason.USER:
            return result.model_copy(
                update={
                    "status": RunStatus.CANCELED,
                    "outcome": RunOutcome.STOPPED,
                    "error_message": "用户已停止运行",
                }
            )
        if self.stop_reason == StopReason.SHUTDOWN:
            return result.model_copy(
                update={
                    "status": RunStatus.STOPPED,
                    "outcome": RunOutcome.STOPPED,
                    "error_message": "Worker 正在关闭，执行已停止",
                }
            )
        if self.stop_reason == StopReason.LEASE_LOST:
            return result.model_copy(
                update={
                    "status": RunStatus.STOPPED,
                    "outcome": RunOutcome.STOPPED,
                    "error_message": "控制面执行租约已失效，执行已停止",
                }
            )
        return result

    async def _report(
        self,
        claim: ClaimResponse,
        result: RunResult,
        workspace: Workspace | None,
        window: ExecutionWindow,
    ) -> None:
        if workspace is not None:
            workspace.write_result(result.model_dump_json(by_alias=True, indent=2))
        payload = result.model_dump(by_alias=True, mode="json")
        payload["workerId"] = self.worker_id
        attempt = 0
        while True:
            try:
                await self.client.complete(claim.task_id, payload)
                return
            except LeaseLostError:
                # The control plane has already rejected this attempt; retrying
                # cannot make the result valid again.
                logger.warning("completion rejected task_id=%s", claim.task_id)
                return
            except ControlPlaneError as exc:
                logger.warning(
                    "completion failed task_id=%s status=%s attempt=%s",
                    claim.task_id,
                    exc.status_code,
                    attempt + 1,
                )
            except Exception:
                logger.exception("completion failed task_id=%s", claim.task_id)
                return
            if not window.alive():
                logger.error("completion abandoned after lease loss task_id=%s", claim.task_id)
                return
            remaining = window.remaining_seconds()
            if remaining <= 0:
                logger.error("completion abandoned after lease loss task_id=%s", claim.task_id)
                return
            delay = min(5.0, 0.5 * (2 ** min(attempt, 4)), remaining)
            if delay <= 0:
                return
            await asyncio.sleep(delay)
            attempt += 1


def _worker_id(settings: Settings) -> str:
    configured = settings.worker.id.strip()
    if configured:
        return configured[:120]
    return f"perf-worker-{socket.gethostname()}-{os.getpid()}"[:120]


def _special_result(
    run_id: str,
    status: RunStatus,
    outcome: RunOutcome,
    started_at: str,
    error_message: str,
) -> RunResult:
    finished = datetime.now(UTC).isoformat()
    return RunResult(
        run_id=run_id,
        status=status,
        outcome=outcome,
        exit_code=-1,
        started_at=started_at,
        finished_at=finished,
        duration_ms=0,
        summary=None,
        flags=[],
        error_message=error_message[:2000],
        log_tail="",
        runner=RunnerInfo(
            hostname=socket.gethostname(),
            cpu_count=os.cpu_count() or 1,
            k6_version="",
        ),
    )


__all__ = ["PerfPoller", "StopReason"]
