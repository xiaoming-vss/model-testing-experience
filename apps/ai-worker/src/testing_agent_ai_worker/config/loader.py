"""Load worker settings from a TOML file."""

from __future__ import annotations

import os
import socket
import tomllib
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from testing_agent_ai_worker.config.models import Settings
from testing_agent_ai_worker.core.errors import ConfigError, safe_validation_summary

DEFAULT_CONFIG_PATH = Path("config/worker.toml")


def load_settings(config_path: str | Path | None = None) -> Settings:
    resolved_path = Path(config_path or DEFAULT_CONFIG_PATH)
    try:
        with resolved_path.open("rb") as config_file:
            payload: dict[str, Any] = tomllib.load(config_file)
    except FileNotFoundError:
        raise ConfigError(f"配置文件不存在: {resolved_path}") from None
    except OSError:
        raise ConfigError(f"无法读取配置文件: {resolved_path}") from None
    except tomllib.TOMLDecodeError:
        raise ConfigError(
            f"配置文件格式错误: {resolved_path}；请检查 TOML 引号、括号和区块格式"
        ) from None
    try:
        settings = Settings.model_validate(payload)
    except ValidationError as exc:
        raise ConfigError(
            f"配置校验失败: {resolved_path}；请检查字段: {safe_validation_summary(exc)}"
        ) from None
    platform_updates = {
        field_name: value
        for field_name, environment_name in {
            "base_url": "TESTING_AGENT_PLATFORM_BASE_URL",
            "worker_token": "TESTING_AGENT_WORKER_TOKEN",
        }.items()
        if (value := os.getenv(environment_name)) is not None
    }
    runtime_overrides = {
        "nanobot": os.getenv("TESTING_AGENT_NANOBOT_RUNTIME_ROOT"),
        "pi": os.getenv("TESTING_AGENT_PI_RUNTIME_ROOT"),
    }
    worker_id = settings.worker.worker_id.strip() or f"ai-worker-{socket.gethostname()}"
    return settings.model_copy(
        update={
            "worker": settings.worker.model_copy(update={"worker_id": worker_id}),
            "platform": settings.platform.model_copy(update=platform_updates),
            "agent": settings.agent.model_copy(
                update={
                    name: getattr(settings.agent, name).model_copy(update={"runtime_root": value})
                    for name, value in runtime_overrides.items()
                    if value is not None
                }
            ),
        }
    )
