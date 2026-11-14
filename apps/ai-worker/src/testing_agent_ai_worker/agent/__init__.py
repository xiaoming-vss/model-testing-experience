"""Execution backend facade.

业务层只从这里选择底座；Nanobot 与 Pi 的具体实现留在各自适配器模块内。
"""

from __future__ import annotations

import os

from testing_agent_ai_worker.agent.base import Agent, AgentConfigPath, AgentResult
from testing_agent_ai_worker.agent.config_builder import task_config_path
from testing_agent_ai_worker.agent.paths import (
    AgentRuntimePaths,
    resolve_runtime_paths,
    resolve_task_workspace,
)

# 预加载进程级清理函数：SIGTERM 处理器不应在信号上下文里触发模块导入。
from testing_agent_ai_worker.agent.pi import (
    check_runtime,
)
from testing_agent_ai_worker.agent.pi import (
    terminate_children as terminate_children_impl,
)
from testing_agent_ai_worker.agent.temp_configs import cleanup_task_configs
from testing_agent_ai_worker.config.models import AgentBackendConfig, NanobotConfig, PiConfig

__all__ = [
    "Agent",
    "AgentBackendConfig",
    "AgentResult",
    "AgentRuntimePaths",
    "apply_environment",
    "cleanup_task_configs",
    "create_agent",
    "migrate_legacy_sessions",
    "resolve_runtime_paths",
    "resolve_task_workspace",
    "task_config_path",
    "terminate_children",
    "verify_runtime",
]


def create_agent(
    *,
    config_path: str | None = None,
    workspace: str | None = None,
    backend: str | None = None,
    tools: tuple[str, ...] | None = None,
) -> Agent:
    """按任务级配置携带的 backend 选择适配器。"""

    resolved_backend = backend or _configured_backend(config_path)
    if resolved_backend not in {"nanobot", "pi"}:
        raise ValueError(f"unsupported agent backend: {resolved_backend}")
    if tools and resolved_backend != "pi":
        raise ValueError("tool selection is only supported by the pi backend")
    if resolved_backend == "pi":
        from testing_agent_ai_worker.agent.pi import Pi

        return Pi.from_config(config_path=config_path, workspace=workspace, tools=tools)

    from testing_agent_ai_worker.agent.nanobot import NanobotAgent

    return NanobotAgent.from_config(
        config_path=config_path,
        workspace=workspace,
        no_tools=tools is not None and not tools,
    )


def _configured_backend(config_path: str | None) -> str:
    if isinstance(config_path, AgentConfigPath):
        return config_path.backend
    return "nanobot"


def verify_runtime(agent_config: AgentBackendConfig) -> None:
    """启动前校验所选底座可用；Nanobot 为进程内 SDK，无需预检。"""

    if isinstance(agent_config, PiConfig):
        check_runtime(agent_config.executable)


def terminate_children() -> None:
    """立即终止 Pi 子进程；Nanobot 后端下为空操作。"""

    terminate_children_impl()


def apply_environment(agent_config: AgentBackendConfig) -> None:
    """把后端配置映射为 SDK 读取的环境变量。"""

    if not isinstance(agent_config, NanobotConfig):
        return
    os.environ["NANOBOT_STREAM_IDLE_TIMEOUT_S"] = f"{agent_config.stream_idle_timeout_seconds:g}"
    if agent_config.provider_request_timeout_seconds is not None:
        os.environ["NANOBOT_OPENAI_COMPAT_TIMEOUT_S"] = (
            f"{agent_config.provider_request_timeout_seconds:g}"
        )


def migrate_legacy_sessions(agent_config: AgentBackendConfig) -> None:
    """迁移历史 Nanobot 会话目录；Pi 后端无历史目录。"""

    if not isinstance(agent_config, NanobotConfig):
        return
    from testing_agent_ai_worker.agent.nanobot import migrate_legacy_sessions as _migrate

    _migrate(agent_config)
