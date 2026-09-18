from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class AiGenerateTaskRequest(BaseModel):
    name: str | None = None
    sprint_id: str | None = Field(default=None)
    requirement_id: str | None = Field(default=None)
    source_type: str | None = Field(default=None)
    source_content: str | None = Field(default=None)
    instruction: str | None = None

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
        json_schema_extra={"additionalProperties": False},
        alias_generator=to_camel,
    )


class AiGenerateTaskRunRequest(BaseModel):
    connection_id: str | None = Field(default=None)
    llm_connection_id: str | None = Field(default=None)
    trigger_type: str | None = Field(default=None)
    checkpoint_enabled: bool | None = Field(default=None)
    config_json: Any | None = Field(default=None)
    result_yaml: str | None = Field(default=None)

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
        json_schema_extra={"additionalProperties": False},
        alias_generator=to_camel,
    )


class RequirementAnalysisRunRequest(BaseModel):
    connection_id: str | None = Field(default=None)
    llm_connection_id: str | None = Field(default=None)
    instruction: str | None = None
    trigger_type: str | None = Field(default=None)
    checkpoint_enabled: bool | None = Field(default=None)
    config_json: Any | None = Field(default=None)
    result_yaml: str | None = Field(default=None)

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
        json_schema_extra={"additionalProperties": False},
        alias_generator=to_camel,
    )


class RequirementAnalysisTaskRequest(BaseModel):
    name: str | None = None
    requirement_id: str | None = Field(default=None)
    instruction: str | None = None

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
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
    gitlab_connection_ids: dict[str, str] = Field(default_factory=dict)
    connection_id: str | None = Field(default=None)
    llm_connection_id: str | None = Field(default=None)
    instruction: str | None = None
    trigger_type: str | None = Field(default=None)
    config_json: Any | None = Field(default=None)
    result_yaml: str | None = Field(default=None)

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
        json_schema_extra={"additionalProperties": False},
        alias_generator=to_camel,
    )


class TestReportGenerateTaskRequest(BaseModel):
    name: str | None = None
    sprint_id: str | None = Field(default=None)
    instruction: str | None = None

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
        json_schema_extra={"additionalProperties": False},
        alias_generator=to_camel,
    )


class TestReportGenerateTaskRunRequest(BaseModel):
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


class AiGenerateTaskReviewRequest(BaseModel):
    llm_connection_id: str | None = None
    action: str | None = None
    review_status: str | None = Field(default=None)
    status: str | None = None
    current_stage: str | None = Field(default=None)
    stage: str | None = None
    review_comment: str | None = Field(default=None)
    comment: str | None = None
    collection_id: str | None = Field(default=None)
    config_json: Any | None = Field(default=None)
    revision_instruction: str | None = Field(default=None)
    result_yaml: str | None = Field(default=None)

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
        json_schema_extra={"additionalProperties": False},
        alias_generator=to_camel,
    )


class AiGenerateTaskResultRequest(BaseModel):
    result_yaml: str = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AiGenerateTaskImportRequest(BaseModel):
    collection_id: str = Field()
    confirm_overwrite: bool = Field(default=False)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class FunctionGenerateTaskImportRequest(BaseModel):
    confirm_overwrite: bool = Field(default=False)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UiGenerateTaskImportRequest(BaseModel):
    suite_id: str = Field()
    confirm_overwrite: bool = Field(default=False)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SourceArchiveResponse(BaseModel):
    archive_id: str = Field()
    filename: str
    size_bytes: int = Field()
    sha256: str
    uploaded_at: datetime = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


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
    source_archive: SourceArchiveResponse | None = Field(default=None)
    instruction: str = ""
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ImportedTarget(BaseModel):
    target_type: Literal["api_collection", "function_suite", "ui_suite"] = Field()
    target_id: str = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AiGenerateTaskRunResponse(BaseModel):
    run_id: str = Field()
    task_id: str = Field()
    requirement_id: str = Field()
    sprint_id: str = Field()
    project_id: str = Field()
    trigger_user_id: str = Field()
    trigger_type: str = Field()
    status: str
    checkpoint_enabled: bool = Field()
    current_stage: str = Field()
    stage_status: str = Field()
    snapshot_json: Any = Field(default_factory=dict)
    error_message: str = Field()
    remediation: str = ""
    config_json: Any = Field(default_factory=dict)
    result_yaml: str = Field()
    result_summary_json: Any = Field(default_factory=dict)
    review_status: str = Field()
    import_status: Literal["pending", "imported"] = Field()
    imported_targets: list[ImportedTarget] = Field(default_factory=list)
    imported_at: datetime | str | None = Field(default=None)
    import_migration_complete: bool = Field()
    reviewer_user_id: str = Field()
    reviewed_at: datetime | str | None = Field(default=None)
    review_comment: str = Field()
    duration_ms: int = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


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

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CodeRiskAnalysisRunResponse(AiGenerateTaskRunResponse):
    """code_risk_analysis 专用 run 响应:追加解析后的 `report` 结构。"""

    report: CodeRiskAnalysisReportResponse | None = None
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiCaseExtractRuleComparison(BaseModel):
    name: str
    enabled: bool
    order_no: int = Field()
    source: str
    source_expr: str = Field()
    var_key: str = Field()
    default_value: str = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiCaseAssertRuleComparison(BaseModel):
    name: str
    enabled: bool
    order_no: int = Field()
    assert_source: str = Field()
    target_expr: str = Field()
    comparator: str
    expected_value: str = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiCaseComparison(BaseModel):
    name: str
    description: str
    enabled: bool
    order_no: int = Field()
    method: str
    url_template: str = Field()
    headers: Any
    query: Any
    body_type: str = Field()
    body_json: Any = Field()
    body_text: str = Field()
    timeout_ms: int = Field()
    continue_on_failure: bool = Field()
    extract_rules: list[ApiCaseExtractRuleComparison] = Field()
    assert_rules: list[ApiCaseAssertRuleComparison] = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiCaseImportConflict(BaseModel):
    normalized_name: str = Field()
    existing_case: ApiCaseComparison = Field()
    generated_case: ApiCaseComparison = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AiGenerateTaskImportResponse(BaseModel):
    requires_confirmation: bool = Field()
    conflicts: list[ApiCaseImportConflict] = Field(default_factory=list)
    run: AiGenerateTaskRunResponse

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class FunctionCaseComparison(BaseModel):
    module: str
    title: str
    preconditions: str
    steps: str
    expected_results: str = Field()
    priority: str
    case_type: str = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class FunctionCaseImportConflict(BaseModel):
    normalized_name: str = Field()
    existing_case: FunctionCaseComparison = Field()
    generated_case: FunctionCaseComparison = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class FunctionGenerateTaskImportResponse(BaseModel):
    requires_confirmation: bool = Field()
    conflicts: list[FunctionCaseImportConflict] = Field(default_factory=list)
    run: AiGenerateTaskRunResponse

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UiCaseComparison(BaseModel):
    name: str
    enabled: bool
    order_no: int = Field()
    steps_json: Any = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UiCaseImportConflict(BaseModel):
    normalized_name: str = Field()
    existing_case: UiCaseComparison = Field()
    generated_case: UiCaseComparison = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UiGenerateTaskImportResponse(BaseModel):
    requires_confirmation: bool = Field()
    conflicts: list[UiCaseImportConflict] = Field(default_factory=list)
    run: AiGenerateTaskRunResponse

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
