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
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal
from uuid import uuid4

from testing_agent_ai_worker.agent.base import AgentResult

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


class Pi:
    """One sequential agent context; each call resumes its named session on disk."""

    def __init__(
        self,
        *,
        config_path: str,
        workspace: str,
        tools: tuple[str, ...] | None = None,
    ) -> None:
        self.config = json.loads(Path(config_path).read_text())
        if not all(self.config.get(key, "").strip() for key in ("model", "api_key", "base_url")):
            raise ValueError("Pi requires platform model credentials")
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.tools = None if tools is None else tuple(tool for tool in tools if tool)
        self._lock = asyncio.Lock()

    @classmethod
    def from_config(
        cls,
        *,
        config_path: str | None = None,
        workspace: str | None = None,
        tools: tuple[str, ...] | None = None,
    ) -> Pi:
        if not config_path or not workspace:
            raise ValueError("Pi requires a task configuration and workspace")
        return cls(config_path=config_path, workspace=workspace, tools=tools)

    async def __aenter__(self) -> Pi:
        return self

    async def __aexit__(self, *_: Any) -> bool:
        return False

    async def run(
        self, message: str, *, session_key: str, media: list[str] | None = None
    ) -> AgentResult:
        async with self._lock:
            return await self._run(message, session_key, media or [])

    async def run_with_subagents(
        self,
        message: str,
        *,
        session_key: str,
        media: list[str] | None = None,
        delegation_kind: Literal[
            "test_points", "detailed_cases", "test_point_review"
        ] = "test_points",
    ) -> AgentResult:
        """Enable the bundled delegation tool for this call only."""
        if delegation_kind not in {"test_points", "detailed_cases", "test_point_review"}:
            raise ValueError("Unsupported subagent task")
        async with self._lock:
            return await self._run(
                message, session_key, media or [], delegation_kind=delegation_kind
            )

    async def _run(
        self,
        message: str,
        session_key: str,
        media: list[str],
        *,
        delegation_kind: Literal["test_points", "detailed_cases", "test_point_review"]
        | None = None,
    ) -> AgentResult:
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
            if delegation_kind:
                context_file = agent_dir / "subagent-input.txt"
                context_file.write_text(message, encoding="utf-8")
                env.update(
                    MTX_SUBAGENT_INPUT=str(context_file),
                    MTX_SUBAGENT_EXECUTABLE=c["executable"],
                    MTX_SUBAGENT_TIMEOUT=str(min(180, c["run_timeout_seconds"])),
                    MTX_SUBAGENT_PULSE=str(min(20, c["stream_idle_timeout_seconds"] / 2)),
                    MTX_SUBAGENT_KIND=delegation_kind,
                )
                command.extend(["--extension", str(Path(__file__).with_name("subagent_skill.mjs"))])
            if self.tools is not None:
                if self.tools:
                    command.extend(["--tools", ",".join(self.tools)])
                else:
                    command.append("--no-tools")
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
            except TimeoutError as error:
                # A bare TimeoutError would reach the platform as an empty failure reason.
                if str(error):
                    raise
                raise TimeoutError(
                    f"模型执行超过 {c['run_timeout_seconds']:g} 秒，执行已终止"
                ) from error
            finally:
                await self._close(process)

    async def _exchange(
        self, process: asyncio.subprocess.Process, message: str, images: list[dict[str, str]]
    ) -> AgentResult:
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
            try:
                line = await asyncio.wait_for(
                    process.stdout.readline(), self.config["stream_idle_timeout_seconds"]
                )
            except TimeoutError as error:
                raise TimeoutError(
                    "模型输出空闲超过 "
                    f"{self.config['stream_idle_timeout_seconds']:g} 秒，执行已终止"
                ) from error
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
            elif kind == "tool_execution_end" and event.get("toolName") == "subagent":
                if event.get("isError"):
                    raise RuntimeError("功能测试子任务执行失败，未生成完整产物")
                details = event.get("result", {}).get("details", {})
                count = details.get("count", 0)
                if isinstance(count, int):
                    usage["subagent_count"] = usage.get("subagent_count", 0) + count
                for key, value in details.get("usage", {}).items():
                    if isinstance(value, (int, float)):
                        child_key = f"subagent_{key}"
                        usage[child_key] = usage.get(child_key, 0) + value
                clarifications = details.get("clarifications", [])
                if clarifications:
                    questions = [
                        item.removeprefix("CLARIFICATION_REQUIRED:").strip()[:2000]
                        for item in clarifications
                        if isinstance(item, str) and item.startswith("CLARIFICATION_REQUIRED:")
                    ]
                    if questions:
                        return AgentResult(
                            content="CLARIFICATION_REQUIRED: " + "\n".join(questions),
                            finish_reason="stop",
                            usage=usage,
                        )
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
        return AgentResult(content=content, finish_reason=reason, usage=usage)

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
