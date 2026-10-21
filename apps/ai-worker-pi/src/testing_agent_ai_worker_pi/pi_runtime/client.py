"""Pi 1.3 RPC boundary: isolated credentials, persistent sessions and bounded cleanup."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import mimetypes
import os
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

PINNED_VERSION = "1.3.0"
_CHILDREN: set[int] = set()
_CHILD_LOCK = threading.Lock()


def check_runtime(executable: str) -> None:
    try:
        result = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=15, check=True
        )
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError("Pi CLI unavailable; install the pinned npm dependency") from None
    if result.stdout.strip() != PINNED_VERSION:
        raise RuntimeError(f"Pi CLI version must be {PINNED_VERSION}")


def terminate_children() -> None:
    with _CHILD_LOCK:
        for pid in tuple(_CHILDREN):
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@dataclass
class PiResult:
    content: str
    finish_reason: str
    usage: dict[str, float] = field(default_factory=dict)


class Pi:
    """One sequential agent context; each call resumes its named session on disk."""

    def __init__(self, *, config_path: str, workspace: str) -> None:
        self.config = json.loads(Path(config_path).read_text())
        if not all(self.config.get(key, "").strip() for key in ("model", "api_key", "base_url")):
            raise ValueError("Pi requires platform model credentials")
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    @classmethod
    def from_config(cls, *, config_path: str | None = None, workspace: str | None = None) -> Pi:
        if not config_path or not workspace:
            raise ValueError("Pi requires a task configuration and workspace")
        return cls(config_path=config_path, workspace=workspace)

    async def __aenter__(self) -> Pi:
        return self

    async def __aexit__(self, *_: Any) -> bool:
        return False

    async def run(
        self, message: str, *, session_key: str, media: list[str] | None = None
    ) -> PiResult:
        async with self._lock:
            return await self._run(message, session_key, media or [])

    async def _run(self, message: str, session_key: str, media: list[str]) -> PiResult:
        c = self.config
        runtime = Path(c["runtime_root"]).resolve()
        sessions = runtime / "sessions"
        sessions.mkdir(parents=True, exist_ok=True, mode=0o700)
        session = sessions / (
            hashlib.sha256((str(self.workspace) + "\0" + session_key).encode()).hexdigest()
            + ".jsonl"
        )
        with TemporaryDirectory(prefix="pi-agent-", dir=runtime) as temp:
            agent_dir = Path(temp)
            model = {
                "id": c["model"],
                "contextWindow": c["context_window_tokens"],
                "maxTokens": c["max_output_tokens"],
                "input": ["text", "image"],
                "reasoning": c["reasoning"],
            }
            models = {
                "providers": {
                    "platform": {
                        "api": c["api"],
                        "baseUrl": c["base_url"],
                        "apiKey": "${MTX_PI_API_KEY}",
                        "models": [model],
                    }
                }
            }
            (agent_dir / "models.json").write_text(json.dumps(models))
            settings = {
                "defaultProvider": "platform",
                "defaultModel": c["model"],
                "defaultThinkingLevel": c["thinking_level"],
                "cacheWarming": "off",
            }
            (agent_dir / "settings.json").write_text(json.dumps(settings))
            env = {
                **os.environ,
                "PI_CODING_AGENT_DIR": temp,
                "MTX_PI_API_KEY": c["api_key"],
                "PI_OFFLINE": "1",
                "PI_TELEMETRY": "0",
            }
            command = [
                c["executable"],
                "--mode",
                "rpc",
                "--offline",
                "--no-extensions",
                "--no-context-files",
                "--no-prompt-templates",
                "--session",
                str(session),
                "--provider",
                "platform",
                "--model",
                c["model"],
            ]
            skills = self.workspace / "skills"
            if skills.is_dir():
                command += ["--skill", str(skills)]
            images = []
            for name in media:
                path = Path(name).resolve()
                mime = mimetypes.guess_type(path.name)[0]
                if mime not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
                    raise ValueError("Unsupported Pi image type")
                images.append(
                    {
                        "type": "image",
                        "mimeType": mime,
                        "data": base64.b64encode(path.read_bytes()).decode(),
                    }
                )
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=self.workspace,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
                limit=32 * 1024 * 1024,
            )
            with _CHILD_LOCK:
                _CHILDREN.add(process.pid)
            try:
                async with asyncio.timeout(c["run_timeout_seconds"]):
                    return await self._exchange(process, message, images)
            finally:
                await self._close(process)

    async def _exchange(
        self, process: asyncio.subprocess.Process, message: str, images: list[dict[str, str]]
    ) -> PiResult:
        request_id = str(uuid4())
        command = {"id": request_id, "type": "prompt", "message": message}
        if images:
            command["images"] = images
        process.stdin.write(json.dumps(command, ensure_ascii=False).encode() + b"\n")
        await process.stdin.drain()
        last: dict[str, Any] | None = None
        accepted = False
        settled = False
        usage: dict[str, float] = {}
        while not (accepted and settled):
            line = await asyncio.wait_for(
                process.stdout.readline(), self.config["stream_idle_timeout_seconds"]
            )
            if not line:
                raise RuntimeError("Pi exited before completing the run")
            try:
                event = json.loads(line)
            except (ValueError, UnicodeError):
                raise RuntimeError("Invalid Pi RPC record") from None
            kind = event.get("type")
            if kind == "response" and event.get("id") == request_id:
                if not event.get("success"):
                    raise RuntimeError("Pi rejected the prompt")
                if event.get("data", {}).get("disposition") == "handled":
                    raise RuntimeError("Pi handled a command without generating an artifact")
                accepted = True
            elif kind == "message_end" and event.get("message", {}).get("role") == "assistant":
                last = event["message"]
                for key, value in last.get("usage", {}).items():
                    if isinstance(value, (int, float)):
                        usage[key] = usage.get(key, 0) + value
            elif kind == "agent_settled":
                settled = True
        if last is None:
            raise RuntimeError("Pi completed without an assistant result")
        reason = last.get("stopReason", "")
        if reason in {"error", "aborted", "length"}:
            # Provider error text can contain authentication headers or private input.
            raise RuntimeError(f"Pi generation ended with {reason}")
        if reason != "stop":
            raise RuntimeError("Pi completed with an unexpected stop reason")
        content = "".join(
            block.get("text", "")
            for block in last.get("content", [])
            if block.get("type") == "text"
        )
        if not content.strip():
            raise RuntimeError("Pi completed without artifact text")
        return PiResult(content=content, finish_reason=reason, usage=usage)

    async def _close(self, process: asyncio.subprocess.Process) -> None:
        try:
            if process.stdin:
                process.stdin.close()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except asyncio.TimeoutError:
                pass
        finally:
            # Also reap tool subprocesses which survived the main Pi process.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
            with _CHILD_LOCK:
                _CHILDREN.discard(process.pid)
