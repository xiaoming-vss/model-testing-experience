"""Pi runtime directory helpers.

调用链路：
- task executors 用它解析 task 运行时 workspace 目录
- `pi_runtime.config_builder` 用它解析临时配置输出目录

这里把运行期目录约定统一收口到 `runtime_root` 下，避免各处自己拼路径。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from testing_agent_ai_worker_pi.config.models import PiConfig
from testing_agent_ai_worker_pi.models.task import Task

DEFAULT_RUNTIME_ROOT = Path("runtime")


@dataclass(frozen=True, slots=True)
class PiRuntimePaths:
    runtime_root: Path
    workspaces_dir: Path
    skills_dir: Path
    temp_configs_dir: Path


def resolve_runtime_paths(pi_config: PiConfig) -> PiRuntimePaths:
    runtime_root = Path(pi_config.runtime_root) if pi_config.runtime_root else DEFAULT_RUNTIME_ROOT
    return PiRuntimePaths(
        runtime_root=runtime_root.resolve(),
        workspaces_dir=runtime_root.resolve() / "workspaces",
        skills_dir=runtime_root.resolve() / "skills",
        # Per-invocation configuration lives under the private runtime root.
        temp_configs_dir=runtime_root.resolve(),
    )


def resolve_task_workspace(pi_config: PiConfig, task: Task) -> Path:
    runtime_paths = resolve_runtime_paths(pi_config)
    workspace_key = task.project_id.strip() or f"task-{task.task_id}"
    project_key = hashlib.sha256(workspace_key.encode()).hexdigest()[:24]
    task_key = hashlib.sha256(task.task_id.encode()).hexdigest()[:24]
    return runtime_paths.workspaces_dir / f"project-{project_key}" / f"task-{task_key}"
