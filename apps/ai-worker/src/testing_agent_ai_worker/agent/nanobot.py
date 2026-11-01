"""Nanobot SDK adapter plus its task-scoped configuration builder."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from testing_agent_ai_worker.agent.base import AgentConfigPath, AgentResult
from testing_agent_ai_worker.agent.paths import resolve_runtime_paths
from testing_agent_ai_worker.agent.temp_configs import tracked
from testing_agent_ai_worker.config.models import NanobotConfig
from testing_agent_ai_worker.models.task import LlmCredentials, Task

# Like worker.toml, resolve deployment configuration from the working directory.
# Installed packages live in site-packages, not under the application root.
DEFAULT_TEMPLATE_PATH = Path("config/nanobot.template.json")

_USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reported_tokens",
    "estimated_tokens",
    "generation_ms",
    "measured_output_tokens",
    "ttft_ms",
    "timed_requests",
    "context_tokens",
    "request_count",
)


class NanobotAgent:
    """Adapt the Nanobot SDK to the shared agent contract."""

    def __init__(self, sdk: Any) -> None:
        self._sdk = sdk

    @classmethod
    def from_config(
        cls, *, config_path: str | None = None, workspace: str | None = None
    ) -> NanobotAgent:
        from nanobot import Nanobot

        return cls(Nanobot.from_config(config_path=config_path, workspace=workspace))

    async def __aenter__(self) -> NanobotAgent:
        await self._sdk.__aenter__()
        return self

    async def __aexit__(self, *exc_info: Any) -> bool:
        return bool(await self._sdk.__aexit__(*exc_info))

    async def run(
        self, message: str, *, session_key: str, media: list[str] | None = None
    ) -> AgentResult:
        result = await self._sdk.run(message, session_key=session_key, media=media)
        reason = result.stop_reason or str(result.metadata.get("finish_reason") or "")
        return AgentResult(
            content=result.content,
            finish_reason=reason,
            usage=_usage_dict(result.usage),
        )


def _usage_dict(usage: Any) -> dict[str, float]:
    if usage is None:
        return {}
    values: dict[str, float] = {}
    for name in _USAGE_FIELDS:
        value = getattr(usage, name, None)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values[name] = float(value)
    return values


def _load_template_config(template_path: Path) -> dict[str, Any]:
    path = template_path
    if not path.exists():
        raise FileNotFoundError(f"nanobot template not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("nanobot template top-level JSON must be an object")
    return payload


def _overlay_llm_credentials(
    *,
    base_config: dict[str, Any],
    credentials: LlmCredentials,
) -> dict[str, Any]:
    agents = base_config.setdefault("agents", {})
    defaults = agents.setdefault("defaults", {})
    if credentials.model.strip():
        defaults["model"] = credentials.model

    providers = base_config.setdefault("providers", {})
    provider_config = providers.setdefault("custom", {})
    if credentials.api_key.strip():
        provider_config["apiKey"] = credentials.api_key
    if credentials.base_url.strip():
        provider_config["apiBase"] = credentials.base_url
    provider_config.setdefault("apiType", "auto")
    return base_config


@contextmanager
def task_config_path(*, agent_config: NanobotConfig, task: Task):
    """返回当前任务应使用的 nanobot config 路径。

    - 所有任务都在 runtime_root 下生成临时配置，固定 SDK 的持久会话根目录
    - 有平台凭证时覆盖模板中的模型连接；任务结束仅删除临时配置文件
    """

    credentials = task.payload.llm_credentials
    runtime_paths = resolve_runtime_paths(agent_config)
    rendered_config = _load_template_config(DEFAULT_TEMPLATE_PATH)
    if credentials is not None:
        rendered_config = _overlay_llm_credentials(
            base_config=rendered_config,
            credentials=credentials,
        )
    runtime_paths.temp_configs_dir.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".json",
        prefix=f"nanobot-task-{task.task_id}-",
        delete=False,
        dir=runtime_paths.temp_configs_dir,
    ) as temp_file:
        json.dump(rendered_config, temp_file, ensure_ascii=False, indent=2)
        temp_path = Path(temp_file.name)

    with tracked(temp_path) as path:
        yield AgentConfigPath(str(path), "nanobot")


def migrate_legacy_sessions(agent_config: NanobotConfig) -> None:
    """Move pre-adaptation sessions before admitting tasks; never overwrite history."""

    root = resolve_runtime_paths(agent_config).runtime_root
    source = root / "temp-configs" / "sessions"
    target = root / "sessions"
    if not source.exists():
        return
    if target.exists():
        raise RuntimeError(f"会话迁移冲突：{source} 和 {target} 同时存在，请先备份并合并后再启动")
    source.rename(target)
