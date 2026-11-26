from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from testing_agent.core.enums import RunStatus


class AiGenerateTaskRunRequest(BaseModel):
    stage: str | None = None
    current_stage: str | None = None
    function_case_ids: list[str] | None = Field(default=None)
    connection_id: str | None = Field(default=None)
    llm_connection_id: str | None = Field(default=None)
    trigger_type: str | None = Field(default=None)
    checkpoint_enabled: bool | None = Field(default=None)
    config_json: Any | None = Field(default=None)
    result_yaml: str | None = Field(default=None)

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        json_schema_extra={"additionalProperties": False},
        alias_generator=to_camel,
    )


class CodeRiskAnalysisTaskRequest(BaseModel):
    name: str | None = None
    requirement_id: str | None = Field(default=None)
    instruction: str | None = None

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
        json_schema_extra={"additionalProperties": False},
        alias_generator=to_camel,
    )


class CodeRiskAnalysisRunRequest(BaseModel):
    request_id: str | None = Field(default=None, min_length=1, max_length=64)
    gitlab_connection_ids: dict[str, str] = Field(default_factory=dict)
    connection_id: str | None = Field(default=None)
    llm_connection_id: str | None = Field(default=None)
    instruction: str | None = None
    trigger_type: str | None = Field(default=None)
    config_json: Any | None = Field(default=None)
    result_yaml: str | None = Field(default=None)

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        json_schema_extra={"additionalProperties": False},
        alias_generator=to_camel,
    )


class RepositoryProfileTaskRequest(BaseModel):
    name: str | None = None
    requirement_id: str | None = Field(default=None)
    instruction: str | None = None

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
        json_schema_extra={"additionalProperties": False},
        alias_generator=to_camel,
    )


class RepositoryProfileRunRequest(BaseModel):
    request_id: str | None = Field(default=None, min_length=1, max_length=64)
    gitlab_connection_ids: dict[str, str] = Field(default_factory=dict)
    connection_id: str | None = Field(default=None)
    llm_connection_id: str | None = Field(default=None)
    instruction: str | None = None
    trigger_type: str | None = Field(default=None)
    config_json: Any | None = Field(default=None)

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        json_schema_extra={"additionalProperties": False},
        alias_generator=to_camel,
    )


class TestReportGenerateTaskRunRequest(BaseModel):
    request_id: str | None = Field(default=None, min_length=1, max_length=64)
    sprint_id: str | None = Field(default=None)
    connection_id: str | None = Field(default=None)
    llm_connection_id: str | None = Field(default=None)
    trigger_type: str | None = Field(default=None)
    snapshot_date: str | None = Field(default=None)
    instruction: str | None = None
    config_json: Any | None = Field(default=None)
    result_yaml: str | None = Field(default=None)

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
        json_schema_extra={"additionalProperties": False},
        alias_generator=to_camel,
    )


class AiGenerateTaskResponse(BaseModel):
    task_id: str = Field()
    task_type: str = Field()
    name: str
    project_id: str = Field()
    sprint_id: str = Field()
    requirement_id: str = Field()
    creator_user_id: str = Field()
    source_type: str = Field()
    source_content: str = Field()
    interface_ids: list[str] = Field(default_factory=list)
    instruction: str = ""
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AiGenerateTaskListItem(BaseModel):
    """Task list summary; source content stays on the detail endpoint."""

    task_id: str = Field()
    task_type: str = Field()
    name: str
    project_id: str = Field()
    sprint_id: str = Field()
    requirement_id: str = Field()
    creator_user_id: str = Field()
    source_type: str = Field()
    interface_count: int = 0
    instruction: str = ""
    latest_run_status: str = ""
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AiGenerateTaskListResponse(BaseModel):
    items: list[AiGenerateTaskListItem]
    total: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ImportedTarget(BaseModel):
    target_type: Literal["api_collection", "function_suite", "ui_suite"] = Field()
    target_id: str = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AiGenerateRunSummary(BaseModel):
    workflow_version: Literal[2] = Field(default=2)
    available_artifacts: list[str] = Field(default_factory=list)
    has_result: bool = False
    created_at: datetime | str | None = None
    started_at: datetime | str | None = None
    finished_at: datetime | str | None = None
    updated_at: datetime | str | None = None
    run_id: str = Field()
    task_id: str = Field()
    requirement_id: str = Field()
    sprint_id: str = Field()
    project_id: str = Field()
    trigger_user_id: str = Field()
    trigger_type: str = Field()
    status: RunStatus
    checkpoint_enabled: bool = Field()
    generation_chain_managed: bool = False
    current_stage: str = Field()
    stage_status: RunStatus | Literal["completed", "waiting_review", ""] = Field()
    error_message: str = Field()
    review_status: str = Field()
    import_status: Literal["pending", "imported"] = Field()
    imported_targets: list[ImportedTarget] = Field(default_factory=list)
    imported_at: datetime | str | None = Field(default=None)
    reviewer_user_id: str = Field()
    reviewed_at: datetime | str | None = Field(default=None)
    review_comment: str = Field()
    duration_ms: int = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AiGenerateRunHistoryResponse(BaseModel):
    items: list[AiGenerateRunSummary]
    total: int
    status_counts: dict[str, int] = Field(default_factory=dict)
    review_pending_count: int = 0
    latest_run: AiGenerateRunSummary | None = None
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AiGenerateTaskRunResponse(AiGenerateRunSummary):
    snapshot_json: Any = Field(default_factory=dict)
    config_json: Any = Field(default_factory=dict)
    result_yaml: str = Field()
    result_summary_json: Any = Field(default_factory=dict)


class CodeRiskAnalysisReportResponse(BaseModel):
    """code_risk_analysis run 的风险报告结构(工单 07,RC-5)。

    四区块 + 各仓库基线/head SHA + 分析时间;区块缺失为 None,
    报告整体缺失或无法解析时 run 的 `report` 字段为 None。
    区块内容由 worker 报告契约决定,保持宽类型透传(不引入
    dict 泛型,避免 OpenAPI 发出 additionalProperties 占位)。
    """

    analyzed_at: str | None = Field(default=None)
    repositories: list[Any] = Field(default_factory=list)
    change_overview: Any | None = Field(default=None)
    risks: list[Any] | None = None
    affected_cases: list[Any] | None = Field(default=None)
    coverage_gaps: list[Any] | None = Field(default=None)
    context_receipt: Any | None = Field(default=None)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CodeRiskAnalysisRunResponse(AiGenerateTaskRunResponse):
    """code_risk_analysis 专用 run 响应:追加解析后的 `report` 结构。"""

    report: CodeRiskAnalysisReportResponse | None = None
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class RepositoryProfileRepositoryResponse(BaseModel):
    repository_id: str
    path_with_namespace: str
    role: Literal["frontend", "backend", "fullstack", "infra", "test", "unknown"]
    responsibility_summary: str
    tech_stack: list[str] = Field(default_factory=list)
    key_paths: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class RepositoryProfileResponse(BaseModel):
    repositories: list[RepositoryProfileRepositoryResponse] = Field(default_factory=list)
    overall_summary: str = ""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class RepositoryProfileRunResponse(AiGenerateTaskRunResponse):
    """repository_profile run 响应:追加解析后的画像结构。"""

    profile: RepositoryProfileResponse | None = None
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
