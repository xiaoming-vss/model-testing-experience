"""k6 subprocess execution."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import signal
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..compiler.compiler import CompiledPlan
from ..core.config import Settings
from ..core.errors import ExecutionError
from ..core.io import write_secure_text
from .summary import read_summary
from .workspace import Workspace

_VERSION_RE = re.compile(r"k6\s+v?(\d+\.\d+\.\d+)")
_LOG_TAIL_BYTES = 8192


@dataclass(frozen=True)
class K6Execution:
    exit_code: int
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    summary: dict[str, Any] | None
    summary_missing: bool
    stopped: bool
    timed_out: bool
    k6_version: str
    log_tail: str
    log_truncated: bool
    error_message: str = ""


class K6Runner:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def check_version(self) -> str:
        binary = self._resolve_binary()
        try:
            process = await asyncio.create_subprocess_exec(
                binary,
                "version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=_minimal_env(),
            )
        except OSError as exc:
            raise ExecutionError(f"无法启动 k6: {binary}") from exc
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise ExecutionError("读取 k6 版本超时") from None

        output = (stdout + stderr).decode("utf-8", errors="replace")
        match = _VERSION_RE.search(output)
        if not match:
            raise ExecutionError("无法识别 k6 版本")
        version = match.group(1)
        expected = self._settings.k6.expected_version.strip().lstrip("v")
        if expected and expected != version:
            raise ExecutionError(f"k6 版本不匹配: 期望 {expected}，实际 {version}")
        return version

    async def run(
        self,
        compiled: CompiledPlan,
        workspace: Workspace,
        stop_event: asyncio.Event | None = None,
    ) -> K6Execution:
        if stop_event is not None and stop_event.is_set():
            raise ExecutionError("任务在启动前已停止")

        binary = self._resolve_binary()
        k6_version = await self.check_version()
        env = self._build_env(compiled, workspace)
        secrets = self._secrets(compiled)
        command = [
            binary,
            "run",
            "--out",
            "experimental-prometheus-rw",
            "--summary-trend-stats",
            compiled.remote_write.trend_stats,
            "--quiet",
            "--no-usage-report",
            "main.js",
        ]

        write_secure_text(workspace.log_path, "", overwrite=True)
        started_at = datetime.now(UTC)
        started_monotonic = time.monotonic()
        stopped = False
        timed_out = False

        with workspace.log_path.open("a", encoding="utf-8", errors="replace") as log_file:
            lock = asyncio.Lock()
            tail = _TailBuffer(_LOG_TAIL_BYTES)
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=str(workspace.root),
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    start_new_session=True,
                )
            except OSError as exc:
                raise ExecutionError(f"无法启动 k6: {binary}") from exc

            readers = [
                asyncio.create_task(_pump(process.stdout, log_file, lock, tail, secrets)),
                asyncio.create_task(_pump(process.stderr, log_file, lock, tail, secrets)),
            ]
            wait_task = asyncio.create_task(process.wait())
            stop_task = asyncio.create_task(stop_event.wait()) if stop_event is not None else None
            try:
                exit_code = await self._wait_for_process(
                    process,
                    wait_task,
                    stop_task,
                    compiled.max_duration_seconds,
                    compiled.stop_grace_seconds,
                )
                if stop_task is not None and stop_task.done():
                    if not wait_task.done():
                        exit_code = await self._terminate(
                            process,
                            wait_task,
                            compiled.stop_grace_seconds,
                        )
                        stopped = True
                    elif exit_code != 0:
                        # The process ended at the same time as the stop request;
                        # a non-zero exit still reflects an interrupted run.
                        stopped = True
                if exit_code is None:
                    timed_out = True
                    exit_code = await self._terminate(
                        process,
                        wait_task,
                        compiled.stop_grace_seconds,
                    )
            finally:
                if stop_task is not None:
                    stop_task.cancel()
                for reader in readers:
                    reader.cancel()
                await asyncio.gather(*readers, return_exceptions=True)
                if not wait_task.done():
                    wait_task.cancel()
                await asyncio.gather(wait_task, return_exceptions=True)

        finished_at = datetime.now(UTC)
        duration_ms = int((time.monotonic() - started_monotonic) * 1000)
        workspace.secure_summary()
        summary, summary_missing = read_summary(
            workspace.summary_path, self._settings.runner.max_summary_mb
        )
        log_tail = tail.text()
        error_message = ""
        if not stopped and not timed_out and exit_code not in (0, 99):
            error_message = _extract_error(log_tail) or f"k6 退出码 {exit_code}"

        return K6Execution(
            exit_code=exit_code,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            summary=summary,
            summary_missing=summary_missing,
            stopped=stopped,
            timed_out=timed_out,
            k6_version=k6_version,
            log_tail=log_tail,
            log_truncated=tail.truncated,
            error_message=error_message,
        )

    async def _wait_for_process(
        self,
        process: asyncio.subprocess.Process,
        wait_task: asyncio.Task[int],
        stop_task: asyncio.Task[bool] | None,
        max_duration_seconds: int,
        stop_grace_seconds: int,
    ) -> int | None:
        if stop_task is None:
            try:
                return await asyncio.wait_for(
                    asyncio.shield(wait_task), timeout=max_duration_seconds
                )
            except TimeoutError:
                return None

        done, _ = await asyncio.wait(
            {wait_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
            timeout=max_duration_seconds,
        )
        if wait_task in done:
            return wait_task.result()
        if stop_task in done:
            return await self._terminate(process, wait_task, stop_grace_seconds)
        return None

    async def _terminate(
        self,
        process: asyncio.subprocess.Process,
        wait_task: asyncio.Task[int],
        grace_seconds: int,
    ) -> int:
        if process.returncode is not None:
            return process.returncode
        _signal_group(process, signal.SIGINT)
        try:
            return await asyncio.wait_for(asyncio.shield(wait_task), timeout=grace_seconds)
        except TimeoutError:
            _signal_group(process, signal.SIGKILL)
            return await wait_task

    def _resolve_binary(self) -> str:
        configured = self._settings.k6.binary
        resolved = shutil.which(configured)
        if resolved is None:
            candidate = Path(configured).expanduser()
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate.resolve())
            raise ExecutionError(f"找不到可执行的 k6: {configured}")
        return resolved

    def _build_env(self, compiled: CompiledPlan, workspace: Workspace) -> dict[str, str]:
        remote_write = compiled.remote_write
        env = _minimal_env()
        env.update(
            {
                "HOME": str(workspace.root),
                "PWD": str(workspace.root),
                "TMPDIR": str(workspace.root),
                "K6_PROMETHEUS_RW_SERVER_URL": remote_write.url,
                "K6_PROMETHEUS_RW_TREND_STATS": remote_write.trend_stats,
                "K6_PROMETHEUS_RW_PUSH_INTERVAL": remote_write.push_interval,
            }
        )
        auth = remote_write.auth
        if auth.type == "basic":
            env["K6_PROMETHEUS_RW_USERNAME"] = auth.username
            env["K6_PROMETHEUS_RW_PASSWORD"] = auth.password.get_secret_value()
        elif auth.type == "bearer":
            env["K6_PROMETHEUS_RW_HTTP_HEADERS"] = (
                "Authorization=Bearer " + auth.token.get_secret_value()
            )
        elif auth.type == "headers":
            env["K6_PROMETHEUS_RW_HTTP_HEADERS"] = ",".join(
                f"{key}={value}" for key, value in auth.headers.items()
            )
        env.update(compiled.env_values)
        return env

    def _secrets(self, compiled: CompiledPlan) -> list[str]:
        auth = compiled.remote_write.auth
        secrets = list(compiled.env_values.values())
        if auth.password.get_secret_value():
            secrets.append(auth.password.get_secret_value())
        if auth.token.get_secret_value():
            secrets.append(auth.token.get_secret_value())
        secrets.extend(auth.headers.values())
        return secrets


def _minimal_env() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
    }


def _signal_group(process: asyncio.subprocess.Process, sig: int) -> None:
    try:
        os.killpg(os.getpgid(process.pid), sig)
    except ProcessLookupError:
        return
    except OSError:
        return


async def _pump(
    stream: asyncio.StreamReader | None,
    log_file: Any,
    lock: asyncio.Lock,
    tail: _TailBuffer,
    secrets: list[str],
) -> None:
    if stream is None:
        return
    while True:
        line = await stream.readline()
        if not line:
            return
        text = redact(line.decode("utf-8", errors="replace"), secrets)
        async with lock:
            log_file.write(text)
            log_file.flush()
            tail.add(text)


def redact(text: str, secrets: list[str]) -> str:
    result = text
    for secret in sorted((value for value in secrets if value), key=len, reverse=True):
        result = result.replace(secret, "***")
    return result


def _extract_error(log_tail: str) -> str:
    for line in reversed(log_tail.splitlines()):
        if "level=error" in line or "ERRO" in line:
            return line.strip()[:500]
    return ""


class _TailBuffer:
    def __init__(self, max_bytes: int) -> None:
        self._max_bytes = max_bytes
        self._parts: list[bytes] = []
        self._size = 0
        self.truncated = False

    def add(self, text: str) -> None:
        data = text.encode("utf-8")
        if len(data) > self._max_bytes:
            data = data[-self._max_bytes :]
            self.truncated = True
        self._parts.append(data)
        self._size += len(data)
        while self._size > self._max_bytes and self._parts:
            first = self._parts[0]
            overflow = self._size - self._max_bytes
            if len(first) <= overflow:
                self._parts.pop(0)
                self._size -= len(first)
            else:
                self._parts[0] = first[overflow:]
                self._size -= overflow
            self.truncated = True

    def text(self) -> str:
        return b"".join(self._parts).decode("utf-8", errors="replace")
