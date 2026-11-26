"""Platform protocol response models for claim/snapshot/llm-credentials."""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from testing_agent_ai_worker.platform.generation_candidates import FrozenCandidateInput

FUNCTIONAL_SOURCE_FORMAT = "requirement_understanding_json"
FUNCTIONAL_SOURCE_FORMAT_VERSION = "0.2"


class PlatformResponseModel(BaseModel):
    """控制面响应允许扩展：新增字段按忽略处理，不阻断滚动升级。

    请求侧与内部产物契约仍按各自模型的严格策略校验；只有控制面响应
    使用本基类，未知字段不会被误当作业务输入。
    """

    model_config = ConfigDict(extra="ignore")


class PlatformClaimTask(PlatformResponseModel):
    task_id: str = Field(validation_alias=AliasChoices("taskId", "task_id", "id"))
    attempt_id: str = Field(default="", validation_alias=AliasChoices("attemptId", "attempt_id"))
    generate_task_id: str = Field(
        default="",
        validation_alias=AliasChoices("generateTaskId", "generate_task_id"),
    )
    task_type: str = Field(validation_alias=AliasChoices("taskType", "task_type", "type"))
    project_id: str = Field(default="", validation_alias=AliasChoices("projectId", "project_id"))
    sprint_id: str = Field(default="", validation_alias=AliasChoices("sprintId", "sprint_id"))
    requirement_id: str = Field(
        default="",
        validation_alias=AliasChoices("requirementId", "requirement_id"),
    )
    lease_seconds: int = Field(
        default=30,
        validation_alias=AliasChoices("leaseSeconds", "lease_seconds"),
    )
    llm_connection_id: str = Field(
        default="",
        validation_alias=AliasChoices("llmConnectionId", "llm_connection_id"),
    )
    checkpoint_enabled: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("checkpointEnabled", "checkpoint_enabled"),
    )
    current_stage: str = Field(
        default="",
        validation_alias=AliasChoices("currentStage", "current_stage"),
    )
    config_json: str = Field(
        default="",
        validation_alias=AliasChoices("configJson", "config_json"),
    )


class PlatformLlmCredentials(PlatformResponseModel):
    base_url: str = Field(validation_alias=AliasChoices("baseUrl", "base_url"))
    model_id: str = Field(validation_alias=AliasChoices("modelId", "model_id"))
    api_key: str = Field(validation_alias=AliasChoices("apiKey", "api_key"))


class PlatformSnapshotRun(PlatformResponseModel):
    workflow_version: int = Field(
        default=2, validation_alias=AliasChoices("workflowVersion", "workflow_version")
    )
    task_id: str = Field(validation_alias=AliasChoices("taskId", "task_id", "id"))
    attempt_id: str = Field(default="", validation_alias=AliasChoices("attemptId", "attempt_id"))
    generate_task_id: str = Field(
        default="",
        validation_alias=AliasChoices("generateTaskId", "generate_task_id"),
    )
    name: str = ""
    project_id: str = Field(default="", validation_alias=AliasChoices("projectId", "project_id"))
    sprint_id: str = Field(default="", validation_alias=AliasChoices("sprintId", "sprint_id"))
    requirement_id: str = Field(
        default="",
        validation_alias=AliasChoices("requirementId", "requirement_id"),
    )
    source_type: str = Field(
        default="",
        validation_alias=AliasChoices("sourceType", "source_type"),
    )
    source_format: str = Field(
        default="",
        validation_alias=AliasChoices("sourceFormat", "source_format"),
    )
    source_format_version: str = Field(
        default="",
        validation_alias=AliasChoices("sourceFormatVersion", "source_format_version"),
    )
    source_content: str = Field(
        default="", validation_alias=AliasChoices("sourceContent", "source_content")
    )
    document_download_url: str = Field(
        default="",
        validation_alias=AliasChoices("documentDownloadUrl", "document_download_url"),
    )
    document_type: str = Field(
        default="",
        validation_alias=AliasChoices("documentType", "document_type"),
    )
    target_scope: str = Field(
        default="",
        validation_alias=AliasChoices("targetScope", "target_scope"),
    )
    instruction: str = ""
    interfaces: list[dict[str, object]] = Field(default_factory=list)
    software_repositories: list[dict[str, object]] = Field(
        default_factory=list,
        validation_alias=AliasChoices("softwareRepositories", "software_repositories"),
    )
    daily_metrics: dict[str, object] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("dailyMetrics", "daily_metrics"),
    )
    # code_risk_analysis 快照字段位于 run 内。
    requirement: dict[str, object] | None = None
    bindings: list[dict[str, object]] = Field(default_factory=list)
    existing_tests: dict[str, object] | None = Field(
        default=None,
        validation_alias=AliasChoices("existingTests", "existing_tests"),
    )
    gitlab_credentials_url: str = Field(
        default="",
        validation_alias=AliasChoices("gitlabCredentialsUrl", "gitlab_credentials_url"),
    )
    # UI 仓库来源快照。
    source_repository: dict[str, object] | None = Field(
        default=None,
        validation_alias=AliasChoices("sourceRepository", "source_repository"),
    )
    source_commit: str = Field(
        default="",
        validation_alias=AliasChoices("sourceCommit", "source_commit"),
    )


class PlatformSnapshotResponse(PlatformResponseModel):
    run: PlatformSnapshotRun
    candidate_protocol: Literal["single-current/1"] | None = Field(
        default=None, validation_alias=AliasChoices("candidateProtocol", "candidate_protocol")
    )
    candidate_input: FrozenCandidateInput | None = Field(
        default=None, validation_alias=AliasChoices("candidateInput", "candidate_input")
    )
    task_type: str = Field(validation_alias=AliasChoices("taskType", "task_type", "type"))
    checkpoint_enabled: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("checkpointEnabled", "checkpoint_enabled"),
    )
    current_stage: str = Field(
        default="",
        validation_alias=AliasChoices("currentStage", "current_stage"),
    )
    config_json: str = Field(
        default="",
        validation_alias=AliasChoices("configJson", "config_json"),
    )

    @model_validator(mode="after")
    def validate_candidate_protocol(self) -> PlatformSnapshotResponse:
        if (self.candidate_protocol is None) != (self.candidate_input is None):
            raise ValueError("candidate protocol and frozen input must occur together")
        return self


class PlatformGitlabCredentials(PlatformResponseModel):
    connection_id: str = Field(
        default="",
        validation_alias=AliasChoices("connectionId", "connection_id"),
    )
    base_url: str = Field(default="", validation_alias=AliasChoices("baseUrl", "base_url"))
    access_token: str = Field(
        default="",
        validation_alias=AliasChoices("accessToken", "access_token"),
    )
    repository_ids: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("repositoryIds", "repository_ids"),
    )


class PlatformGitlabCredentialsResponse(PlatformResponseModel):
    task_id: str = Field(default="", validation_alias=AliasChoices("taskId", "task_id"))
    bindings: list[dict[str, object]] = Field(default_factory=list)
    credentials: list[PlatformGitlabCredentials] = Field(default_factory=list)
