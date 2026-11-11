"""Typed worker configuration models."""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, Field


class WorkerConfig(BaseModel):
    worker_id: str = "testing-agent-ai-worker"
    poll_interval_seconds: int = 10
    heartbeat_interval_seconds: int = 15
    max_concurrent_tasks: int = 2
    run_once: bool = False


class PlatformConfig(BaseModel):
    base_url: str = ""
    worker_token: str = ""
    task_claim_path: str = "/internal/ai-worker/tasks/claim"
    task_snapshot_path: str = "/internal/ai-worker/tasks/{task_id}/snapshot"
    task_started_path: str = "/internal/ai-worker/tasks/{task_id}/started"
    task_heartbeat_path: str = "/internal/ai-worker/tasks/{task_id}/heartbeat"
    task_progress_path: str = "/internal/ai-worker/tasks/{task_id}/progress"
    task_completed_path: str = "/internal/ai-worker/tasks/{task_id}/completed"
    task_llm_credentials_path: str = "/internal/ai-worker/tasks/{task_id}/llm-credentials"
    request_timeout_seconds: float = 60.0


class NanobotConfig(BaseModel):
    backend: Literal["nanobot"] = "nanobot"
    runtime_root: str = ""
    stream_idle_timeout_seconds: float = Field(default=300.0, gt=0, allow_inf_nan=False)
    provider_request_timeout_seconds: float | None = None


class PiConfig(BaseModel):
    backend: Literal["pi"] = "pi"
    runtime_root: str = ""
    stream_idle_timeout_seconds: float = Field(default=300.0, gt=0, allow_inf_nan=False)
    executable: str = "pi"
    run_timeout_seconds: float = Field(default=1800, gt=0, allow_inf_nan=False)
    api: Literal["openai-completions", "openai-responses", "anthropic-messages"] = (
        "openai-completions"
    )
    context_window_tokens: int = Field(default=500000, gt=0)
    max_output_tokens: int = Field(default=65536, gt=0)
    reasoning: bool = False
    thinking_level: Literal["off", "minimal", "low", "medium", "high", "xhigh", "max"] = "off"


AgentBackendConfig: TypeAlias = NanobotConfig | PiConfig


class AgentConfig(BaseModel):
    """执行底座选择：`backend` 决定实际生效的子配置。"""

    backend: Literal["nanobot", "pi"] = "nanobot"
    nanobot: NanobotConfig = NanobotConfig()
    pi: PiConfig = PiConfig()

    @property
    def active(self) -> AgentBackendConfig:
        return self.pi if self.backend == "pi" else self.nanobot


class CodeRiskAnalysisConfig(BaseModel):
    gitlab_timeout_seconds: float = 120.0
    git_timeout_seconds: float = Field(default=300.0, gt=0, allow_inf_nan=False)
    workspace_retention_hours: float = Field(default=24.0, gt=0, allow_inf_nan=False)
    max_diff_chars: int = Field(default=1_000_000, gt=0)
    max_repos: int = Field(default=20, gt=0)


class RepositoryProfileConfig(BaseModel):
    git_timeout_seconds: float = Field(default=300.0, gt=0, allow_inf_nan=False)
    workspace_retention_hours: float = Field(default=24.0, gt=0, allow_inf_nan=False)
    max_repos: int = Field(default=20, gt=0)
    max_output_chars: int = Field(default=100_000, gt=0)


class UiGenerationConfig(BaseModel):
    """UI 生成仓库源码准备:单仓库 checkout 的超时、保留和大小限制。"""

    git_timeout_seconds: float = Field(default=300.0, gt=0, allow_inf_nan=False)
    workspace_retention_hours: float = Field(default=24.0, gt=0, allow_inf_nan=False)
    # 只统计 checkout 后的工作树(不含 .git);超限直接失败,避免把异常大仓库交给模型。
    max_repo_size_mb: float = Field(default=500.0, gt=0, allow_inf_nan=False)
    max_repo_files: int = Field(default=200_000, gt=0)


class LoggingConfig(BaseModel):
    level: str = "INFO"
    console: bool = True
    dir: str = "logs"
    filename: str = "worker.log"
    retention_days: int = 7


class Settings(BaseModel):
    worker: WorkerConfig = WorkerConfig()
    platform: PlatformConfig = PlatformConfig()
    agent: AgentConfig = AgentConfig()
    code_risk_analysis: CodeRiskAnalysisConfig = CodeRiskAnalysisConfig()
    repository_profile: RepositoryProfileConfig = RepositoryProfileConfig()
    ui_generation: UiGenerationConfig = UiGenerationConfig()
    logging: LoggingConfig = LoggingConfig()
