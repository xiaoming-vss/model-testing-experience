"""Configuration loading for the performance worker.

The worker intentionally has no field-level environment overrides. The only
environment input is ``APP_CONF``, used as a config path fallback. Deployment
configuration is generated from ``config/platform.toml`` by
``scripts/manage.py`` into ``config/local.toml``.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from .errors import ConfigError


class ControlPlaneSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = ""
    worker_token: SecretStr = SecretStr("")
    timeout_seconds: float = Field(default=15, ge=1, le=120)
    retry_attempts: int = Field(default=3, ge=1, le=10)


class WorkerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = ""
    health_file: str = "./runtime/health.json"
    health_max_age_seconds: int = Field(default=90, ge=30, le=300)
    poll_interval_seconds: float = Field(default=2, ge=0.5, le=60)
    heartbeat_interval_seconds: float = Field(default=10, ge=1, le=60)
    lease_margin_seconds: int = Field(default=5, ge=0, le=30)
    shutdown_grace_seconds: int = Field(default=60, ge=1, le=600)


class K6Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    binary: str = "k6"
    expected_version: str = ""


class RunnerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_root: str = "./runtime/runs"
    max_duration_seconds: int = Field(default=3600, ge=1, le=86400)
    stop_grace_seconds: int = Field(default=30, ge=1, le=600)
    keep_failed_workspace_hours: int = Field(default=24, ge=0, le=720)
    max_data_file_mb: int = Field(default=50, ge=1, le=1024)
    max_summary_mb: int = Field(default=20, ge=1, le=1024)


class OnceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_file: str = ""


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["once", "poll"] = "once"
    control_plane: ControlPlaneSettings = Field(default_factory=ControlPlaneSettings)
    worker: WorkerSettings = Field(default_factory=WorkerSettings)
    k6: K6Settings = Field(default_factory=K6Settings)
    runner: RunnerSettings = Field(default_factory=RunnerSettings)
    once: OnceSettings = Field(default_factory=OnceSettings)


def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load and resolve the worker configuration.

    Precedence: explicit path, ``APP_CONF``, ``./config/local.toml``, then the
    project-local ``config/local.toml``. Relative runtime paths are resolved
    against the current working directory, matching ``scripts/manage.py run``.
    """

    path = _resolve_config_path(config_path)
    try:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
    except OSError as exc:
        raise ConfigError(f"无法读取配置文件: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"配置文件不是合法 TOML: {path}") from exc

    try:
        settings = Settings.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"配置校验失败: {_format_validation_error(exc)}") from None

    return _resolve_runtime_paths(settings)


def _resolve_config_path(config_path: str | Path | None) -> Path:
    if config_path is not None:
        path = Path(config_path).expanduser()
        if not path.is_file():
            raise ConfigError(f"配置文件不存在: {path}")
        return path.resolve()

    env_path = os.environ.get("APP_CONF", "").strip()
    if env_path:
        path = Path(env_path).expanduser()
        if not path.is_file():
            raise ConfigError(f"APP_CONF 指向的配置文件不存在: {path}")
        return path.resolve()

    candidates = (
        Path.cwd() / "config" / "local.toml",
        _project_root() / "config" / "local.toml",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise ConfigError("缺少配置文件；请使用 --config 或设置 APP_CONF")


def _resolve_runtime_paths(settings: Settings) -> Settings:
    cwd = Path.cwd()
    settings.worker.health_file = str(_absolute(cwd, settings.worker.health_file))
    settings.runner.workspace_root = str(_absolute(cwd, settings.runner.workspace_root))
    if settings.once.snapshot_file:
        settings.once.snapshot_file = str(_absolute(cwd, settings.once.snapshot_file))
    return settings


def _absolute(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _format_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors(include_url=False, include_input=False):
        location = ".".join(str(item) for item in error["loc"])
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts) or "unknown"
