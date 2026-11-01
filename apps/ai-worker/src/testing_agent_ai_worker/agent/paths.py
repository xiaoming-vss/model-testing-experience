"""Runtime directory helpers shared by both execution backends.

调用链路：
- task executors 用它解析 task 运行时 workspace 目录
- `agent.config_builder` 用它解析临时配置输出目录

这里把运行期目录约定统一收口到 `runtime_root` 下，避免各处自己拼路径。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from testing_agent_ai_worker.config.models import AgentBackendConfig, PiConfig
from testing_agent_ai_worker.models.task import Task

DEFAULT_PI_RUNTIME_ROOT = Path("runtime")
# Nanobot 0.3.5 stores sessions beside the loaded configuration file.
DEFAULT_NANOBOT_RUNTIME_ROOT = Path(__file__).resolve().parents[3] / "runtime" / "nanobot"


@dataclass(frozen=True, slots=True)
class AgentRuntimePaths:
    runtime_root: Path
    workspaces_dir: Path
    skills_dir: Path
    temp_configs_dir: Path


def resolve_runtime_paths(agent_config: AgentBackendConfig) -> AgentRuntimePaths:
    default_root = (
        DEFAULT_PI_RUNTIME_ROOT
        if isinstance(agent_config, PiConfig)
        else DEFAULT_NANOBOT_RUNTIME_ROOT
    )
    runtime_root = Path(agent_config.runtime_root) if agent_config.runtime_root else default_root
    resolved_root = runtime_root.resolve()
    return AgentRuntimePaths(
        runtime_root=resolved_root,
        workspaces_dir=resolved_root / "workspaces",
        skills_dir=resolved_root / "skills",
        # Per-invocation configuration lives under the private runtime root.
        temp_configs_dir=resolved_root,
    )


def resolve_task_workspace(agent_config: AgentBackendConfig, task: Task) -> Path:
    runtime_paths = resolve_runtime_paths(agent_config)
    workspace_key = task.project_id.strip() or f"task-{task.task_id}"
    project_key = hashlib.sha256(workspace_key.encode()).hexdigest()[:24]
    task_key = hashlib.sha256(task.task_id.encode()).hexdigest()[:24]
    return runtime_paths.workspaces_dir / f"project-{project_key}" / f"task-{task_key}"
