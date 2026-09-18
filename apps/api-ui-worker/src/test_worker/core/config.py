"""
配置管理模块
从 config.toml 加载配置
"""

from __future__ import annotations

import os
import socket
import tomllib
from pathlib import Path
from typing import Any

from ..contracts.types import WorkerConfig, WorkerMode


TomlConfig = dict[str, Any]


def _config_value(config: TomlConfig, section: str, key: str, default: Any) -> Any:
    section_value = config.get(section, {})
    if not isinstance(section_value, dict):
        return default
    value = section_value.get(key, default)
    return default if value is None else value


def _config_string(config: TomlConfig, section: str, key: str, default: str = "") -> str:
    return str(_config_value(config, section, key, default)).strip()


def _config_int(config: TomlConfig, section: str, key: str, default: int) -> int:
    value = _config_value(config, section, key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _config_bool(config: TomlConfig, section: str, key: str, default: bool) -> bool:
    value = _config_value(config, section, key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    return bool(value)


def _resolve_worker_id(default_worker_id: str = "") -> str:
    """解析 worker ID；未配置时使用 hostname 和 pid 生成。"""
    if default_worker_id.strip():
        return default_worker_id.strip()
    hostname = socket.gethostname()
    pid = os.getpid()
    return f"api-ui-worker-{hostname}-{pid}"


def load_config() -> WorkerConfig:
    """加载工作配置。"""
    toml_config = _load_toml_config()

    mode_default = str(toml_config.get("mode", "poll"))
    mode_str = mode_default.strip()
    mode: WorkerMode = "once" if mode_str == "once" else "poll"

    artifacts_dir = _config_string(toml_config, "ui", "artifacts_dir", "./artifacts")
    artifacts_root_dir = str(Path(artifacts_dir).resolve())

    return WorkerConfig(
        mode=mode,
        worker_id=_resolve_worker_id(_config_string(toml_config, "worker", "id")),
        control_plane_base_url=_config_string(toml_config, "control_plane", "base_url"),
        worker_token=_config_string(toml_config, "control_plane", "worker_token"),
        poll_interval_ms=_config_int(toml_config, "worker", "poll_interval_ms", 3000),
        request_timeout_ms=_config_int(toml_config, "worker", "request_timeout_ms", 15000),
        heartbeat_interval_ms=_config_int(toml_config, "worker", "heartbeat_interval_ms", 10000),
        artifacts_root_dir=artifacts_root_dir,
        default_headless=_config_bool(toml_config, "ui", "headless", True),
        default_slow_mo_ms=_config_int(toml_config, "ui", "slow_mo_ms", 0),
        trace_enabled=_config_bool(toml_config, "ui", "trace_enabled", True),
        screenshot_on_failure=_config_bool(toml_config, "ui", "screenshot_on_failure", True),
        snapshot_file=_config_string(toml_config, "once", "snapshot_file"),
        artifacts_bind_host=_config_string(toml_config, "ui", "artifacts_bind_host", "127.0.0.1"),
        artifacts_port=_config_int(toml_config, "ui", "artifacts_port", 9010),
        artifacts_base_url=_config_string(toml_config, "ui", "artifacts_base_url"),
    )


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_toml_config() -> TomlConfig:
    """加载 config.toml。当前目录优先，项目根目录兜底。"""
    config_candidates = [
        Path.cwd() / "config.toml",
        _project_root() / "config.toml",
    ]
    loaded: set[str] = set()
    for file_path in config_candidates:
        file_str = str(file_path)
        if file_str in loaded or not file_path.exists():
            continue
        loaded.add(file_str)
        with file_path.open("rb") as f:
            parsed = tomllib.load(f)
        return parsed if isinstance(parsed, dict) else {}
    return {}
