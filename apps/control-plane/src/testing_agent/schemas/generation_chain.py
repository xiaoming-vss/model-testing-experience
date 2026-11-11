"""HTTP contracts for the requirement generation chain workspace."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from testing_agent.schemas.requirement_design import DesignKind

ChainStageState = Literal[
    "approved", "draft", "invalid", "running", "failed", "not_started", "imported"
]


class ChainModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class ChainSourceRepositoryView(ChainModel):
    repository_id: str = ""
    path_with_namespace: str = ""
    branch: str = ""
    commit: str = ""
    commit_mode: str = ""
    profile_version_id: str = ""
    profile_version_no: int = 0
    resolved_at: datetime | str | None = None


class ChainSourceInputsView(ChainModel):
    source_kind: Literal["repository"] = "repository"
    repository: ChainSourceRepositoryView
    # Formal functional cases are free-form imported content and stay untyped here.
    cases: list[Any] = Field(default_factory=list)


class UiSourceRepositoryOption(ChainModel):
    repository_id: str
    path_with_namespace: str = ""
    role: str = "unknown"
    confidence: float | None = None
    responsibility_summary: str = ""
    tech_stack: list[str] = Field(default_factory=list)
    key_paths: list[str] = Field(default_factory=list)
    branch: str = ""
    commit: str = ""
    is_frontend: bool = False
    available: bool = False
    profile_error: str = ""


class UiSourceProfileVersion(ChainModel):
    version_id: str
    version_no: int
    label: str = ""
    source_run_id: str = ""
    created_at: datetime | str | None = None
    overall_summary: str = ""
    repositories: list[UiSourceRepositoryOption] = Field(default_factory=list)
    default_repository_id: str = ""


class UiGenerationSourceOptions(ChainModel):
    profile_versions: list[UiSourceProfileVersion] = Field(default_factory=list)
    default_profile_version_id: str = ""
    default_repository_id: str = ""


class UiGenerationSourceCheckRequest(ChainModel):
    profile_version_id: str = Field(min_length=1, max_length=64)
    repository_id: str = Field(min_length=1, max_length=64)
    pinned_commit: str = Field(min_length=1, max_length=128)
    gitlab_connection_id: str = Field(default="", max_length=64)


class UiGenerationSourceCheck(ChainModel):
    repository_id: str
    branch: str
    pinned_commit: str
    current_commit: str
    changed: bool


class ChainStageVersionSummary(ChainModel):
    version_id: str
    stage: str = ""
    stage_label: str = ""
    version_no: int
    label: str
    summary: str
    artifact_format: str
    created_at: datetime | str | None = None
    reviewer_user_id: str = ""
    source_run_id: str = ""
    source_batch_id: str = ""
    imported: bool = False


class ChainStageDraftView(ChainModel):
    attempt_id: str
    run_id: str
    status: str
    summary: str
    artifact_format: str
    content: str
    revision: int
    base_version_id: str = ""
    base_version_label: str = ""
    upstream_versions: dict[str, str] = Field(default_factory=dict)
    source_inputs: ChainSourceInputsView | None = None
    instruction: str = ""
    invalidated: bool = False
    invalidated_reason: str = ""
    created_at: datetime | str | None = None


class ChainStageView(ChainModel):
    stage: str
    label: str
    order: int
    state: ChainStageState
    latest_version: ChainStageVersionSummary | None = None
    draft: ChainStageDraftView | None = None
    versions: list[ChainStageVersionSummary] = Field(default_factory=list)
    upstream_stages: list[str] = Field(default_factory=list)
    blocked_reason: str = ""
    error_message: str = ""
    failure_run_id: str = ""
    failed_at: datetime | str | None = None
    active_run_id: str = ""


class ChainLeafView(ChainModel):
    stage: str = ""
    version_id: str = ""
    version_no: int = 0
    imported: bool = False
    imported_targets: list[dict[str, str]] = Field(default_factory=list)
    imported_at: datetime | str | None = None


class GenerationChainView(ChainModel):
    kind: DesignKind
    label: str
    configured: bool
    task_id: str = ""
    run_id: str = ""
    source_batch_id: str = ""
    active: bool = False
    busy: bool = False
    source_inputs: ChainSourceInputsView | None = None
    source_changed: bool = False
    updated_at: datetime | str | None = None
    draft_count: int = 0
    continuation_error: str = ""
    stages: list[ChainStageView] = Field(default_factory=list)
    leaf: ChainLeafView = Field(default_factory=ChainLeafView)


class GenerationChainOverview(ChainModel):
    chains: list[GenerationChainView]


class GenerationChainVersionDetail(ChainModel):
    version_id: str
    kind: DesignKind
    stage: str
    stage_label: str
    version_no: int
    label: str
    summary: str
    artifact_format: str
    content: str
    reviewer_user_id: str = ""
    reviewed_at: datetime | str | None = None
    review_comment: str = ""
    upstream_versions: dict[str, str] = Field(default_factory=dict)
    upstream: list[ChainStageVersionSummary] = Field(default_factory=list)
    source_inputs: ChainSourceInputsView | None = None


class GenerationChainRunRequest(ChainModel):
    # Refresh starts a new UI run; omitted fields preserve existing input snapshots.
    refresh_inputs: bool = False
    function_case_ids: list[str] | None = None
    connection_id: str = Field(min_length=1, max_length=64)
    request_id: UUID | None = None
    instruction: str | None = None
    config_json: Any | None = None
    upstream_versions: dict[str, str] = Field(default_factory=dict)
    # UI surface only: the selected profile pin. Other stages and kinds reject them.
    source_profile_version_id: str | None = Field(default=None, max_length=64)
    source_repository_id: str | None = Field(default=None, max_length=64)
    source_commit_mode: Literal["profile", "latest"] = "profile"
    gitlab_connection_id: str = Field(default="", max_length=64)


class GenerationChainRevisionRequest(ChainModel):
    connection_id: str = Field(min_length=1, max_length=64)
    instruction: str = Field(min_length=1, max_length=4000)
    request_id: UUID | None = None
    attachment_file_ids: list[str] = Field(default_factory=list, max_length=6)


class GenerationChainReviewRequest(ChainModel):
    action: Literal["approve", "reject"]
    expected_attempt_id: str | None = Field(default=None, min_length=1, max_length=64)
    continue_after: bool = False
    comment: str = Field(default="", max_length=4000)
    instruction: str | None = None
    connection_id: str | None = Field(default=None, max_length=64)
    request_id: UUID | None = None


class GenerationChainSaveDraftRequest(ChainModel):
    expected_attempt_id: str = Field(min_length=1, max_length=64)
    content: str


class GenerationChainDeleteVersionResponse(ChainModel):
    version_id: str
    deleted: bool
    invalidated_draft_count: int = 0


class ChainImportRecordView(ChainModel):
    import_id: str
    version_id: str
    version_no: int = 0
    version_label: str = ""
    leaf_stage: str = ""
    parent_versions: dict[str, str] = Field(default_factory=dict)
    changed_case_ids: list[str] = Field(default_factory=list)
    changed_case_count: int = 0
    target_case_count: int = 0
    mixed_source: bool = False
    imported_by: str = ""
    imported_at: datetime | str | None = None
    review_comment: str = ""


class ChainImportTargetView(ChainModel):
    target_type: Literal["function_suite", "api_collection", "ui_suite"]
    target_id: str
    name: str
    case_count: int = 0
    effective_import_id: str = ""
    effective_import: ChainImportRecordView | None = None
    source_deleted: bool = False


class GenerationChainImportOptions(ChainModel):
    kind: DesignKind
    version_id: str
    version_label: str
    leaf_stage: str
    parent_versions: dict[str, str] = Field(default_factory=dict)
    parents: list[ChainStageVersionSummary] = Field(default_factory=list)
    targets: list[ChainImportTargetView] = Field(default_factory=list)
    target_required: bool = True


class GenerationChainImportRequest(ChainModel):
    target_id: str = Field(default="", max_length=64)
    confirm_overwrite: bool = False


class GenerationChainImportResponse(ChainModel):
    requires_confirmation: bool = False
    conflicts: list[Any] = Field(default_factory=list)
    imported: bool = False
    target_id: str = ""
    target_type: str = ""
    changed_case_ids: list[str] = Field(default_factory=list)
    changed_case_count: int = 0
    import_record: ChainImportRecordView | None = None
    import_records: list[ChainImportRecordView] = Field(default_factory=list)
    chain: GenerationChainView | None = None
