"""Task-scoped configuration files, dispatched by execution backend."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from testing_agent_ai_worker.agent.base import AgentConfigPath
from testing_agent_ai_worker.agent.paths import resolve_runtime_paths
from testing_agent_ai_worker.agent.temp_configs import tracked
from testing_agent_ai_worker.config.models import AgentBackendConfig, PiConfig
from testing_agent_ai_worker.models.task import Task


@contextmanager
def task_config_path(*, agent_config: AgentBackendConfig, task: Task) -> Iterator[str]:
    """生成当前任务使用的后端配置，并在任务结束后删除。"""

    if isinstance(agent_config, PiConfig):
        builder = _pi_task_config_path
    else:
        from testing_agent_ai_worker.agent.nanobot import task_config_path as builder
    with builder(agent_config=agent_config, task=task) as path:
        yield path


@contextmanager
def _pi_task_config_path(*, agent_config: PiConfig, task: Task) -> Iterator[str]:
    credentials = task.payload.llm_credentials
    runtime = resolve_runtime_paths(agent_config)
    runtime.temp_configs_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {
        **agent_config.model_dump(),
        "runtime_root": str(runtime.runtime_root),
        "model": credentials.model if credentials else "",
        "base_url": credentials.base_url if credentials else "",
        "api_key": credentials.api_key if credentials else "",
    }
    # 后端选择由 AgentConfigPath 携带，配置内容只保留 Pi 自身字段。
    payload.pop("backend", None)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".json",
        prefix="pi-task-",
        dir=runtime.temp_configs_dir,
        delete=False,
    ) as stream:
        json.dump(payload, stream)
        path = Path(stream.name)

    with tracked(path) as tracked_path:
        yield AgentConfigPath(str(tracked_path), "pi")
