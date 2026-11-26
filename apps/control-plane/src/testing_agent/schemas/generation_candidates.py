"""Multi-candidate generation, review and current-content contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator
from pydantic.alias_generators import to_camel

from testing_agent.schemas.generation_chain import ChainSourceInputsView

ChainKind = Literal["requirement_analysis", "function", "api", "ui"]
CandidateDisposition = Literal["available", "rejected"]
AdoptionBlockReason = Literal[
    "source_stale",
    "source_unknown",
    "source_conflict",
    "concurrent_change",
]
Identifier = Annotated[str, Field(min_length=1, max_length=64)]


class CandidateContract(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class SourceSelection(CandidateContract):
    chain_kind: ChainKind
    stage: Identifier
    source_kind: Literal["current", "candidate"]
    candidate_id: Identifier | None = None
    snapshot_id: Identifier | None = None
    expected_candidate_token: Identifier | None = None
    expected_current_token: Identifier | None = None

    @model_validator(mode="after")
    def validate_source_identity(self) -> SourceSelection:
        candidate_fields = (self.candidate_id, self.snapshot_id, self.expected_candidate_token)
        if self.source_kind == "candidate":
            if not all(candidate_fields) or self.expected_current_token is not None:
                raise ValueError("candidate source requires its identity, snapshot and token")
        elif (
            any(value is not None for value in candidate_fields) or not self.expected_current_token
        ):
            raise ValueError("current source requires only the current token")
        return self


class CandidateRunRequest(CandidateContract):
    connection_id: Identifier
    generation_mode: Literal["current", "trial"] = "current"
    request_id: UUID | None = None
    source_selections: list[SourceSelection] = Field(default_factory=list)
    required_current_source: SourceSelection | None = None
    refresh_inputs: bool = False
    function_case_ids: list[Identifier] | None = None
    instruction: str | None = None
    config_json: Any | None = None
    source_repository_id: Identifier | None = None
    source_profile_candidate_id: Identifier | None = None
    source_commit_mode: Literal["profile", "latest"] = "profile"
    gitlab_connection_id: str = Field(default="", max_length=64)

    @model_validator(mode="after")
    def validate_selections(self) -> CandidateRunRequest:
        if self.generation_mode == "current" and self.source_selections:
            raise ValueError("current mode resolves its upstream inputs on the server")
        if self.required_current_source is not None and (
            self.generation_mode != "current"
            or self.required_current_source.source_kind != "current"
        ):
            raise ValueError("a required current source is valid only for current mode")
        nodes = [(source.chain_kind, source.stage) for source in self.source_selections]
        if len(nodes) != len(set(nodes)):
            raise ValueError("each upstream stage may have only one selected source")
        return self


class CandidateSummaryView(CandidateContract):
    candidate_id: Identifier
    snapshot_id: Identifier
    candidate_token: Identifier
    current_attempt_id: Identifier | None = None
    derived_from_candidate_id: Identifier | None = None
    disposition: CandidateDisposition
    generation_mode: Literal["current", "trial"]
    frozen_at: datetime | None = None
    # Empty means a legacy attempt was removed and its initiator is unknown.
    created_by: str = Field(max_length=64)
    created_at: datetime
    is_current: bool


class CandidateSourceTraceView(CandidateContract):
    """Compact upstream selection for review-side source trace."""

    chain_kind: ChainKind
    stage: Identifier
    source_kind: Literal["current", "candidate"]
    candidate_id: Identifier
    snapshot_id: Identifier


class CandidateBasisSourceView(CandidateContract):
    """One frozen stage snapshot in a candidate/current content's full basis."""

    chain_kind: ChainKind
    stage: Identifier
    source_kind: Literal["current", "candidate"] | None = None
    candidate_id: Identifier
    snapshot_id: Identifier
    direct: bool = False


class CandidateListView(CandidateContract):
    items: list[CandidateSummaryView]
    total: int
    page: int
    page_size: int


class CandidateDetailView(CandidateSummaryView):
    content: str
    format: str
    source_inputs: ChainSourceInputsView | None = None
    material_content: str | None = None
    source_trace: list[CandidateSourceTraceView] = Field(default_factory=list)
    basis_sources: list[CandidateBasisSourceView] = Field(default_factory=list)


class FrozenCandidateSource(CandidateContract):
    requirement_id: Identifier
    chain_kind: ChainKind
    stage: Identifier
    source_kind: Literal["current", "candidate"] | None = None
    candidate_id: Identifier | None = None
    snapshot_id: Identifier
    content_hash: str = Field(min_length=1, max_length=128)
    basis_hash: str = Field(min_length=1, max_length=128)
    source_batch_id: Identifier | None = None
    parent_snapshot_ids: list[Identifier] = Field(default_factory=list)
    root_snapshot_ids: list[Identifier] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_candidate_identity(self) -> FrozenCandidateSource:
        if self.source_kind == "candidate" and not self.candidate_id:
            raise ValueError("candidate source requires a candidate identity")
        return self


class FrozenRootSource(CandidateContract):
    snapshot_id: Identifier
    resource_kind: Identifier
    resource_id: Identifier
    content_hash: str = Field(min_length=1, max_length=128)
    source_batch_id: Identifier | None = None


class FrozenSelectedSource(CandidateContract):
    """How this run selected an already resolved stage snapshot."""

    chain_kind: ChainKind
    stage: Identifier
    source_kind: Literal["current", "candidate"]
    candidate_id: Identifier
    snapshot_id: Identifier


class FrozenCandidateInput(CandidateContract):
    generation_mode: Literal["current", "trial"]
    lineage_hash: str = Field(min_length=1, max_length=128)
    sources: list[FrozenCandidateSource] = Field(default_factory=list)
    root_sources: list[FrozenRootSource] = Field(default_factory=list)
    selected_sources: list[FrozenSelectedSource] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_selected_sources(self) -> FrozenCandidateInput:
        keys = [(item.chain_kind, item.stage) for item in self.selected_sources]
        if len(keys) != len(set(keys)):
            raise ValueError("each selected stage must occur once")
        known = {
            (item.chain_kind, item.stage, item.candidate_id, item.snapshot_id)
            for item in self.sources
        }
        for item in self.selected_sources:
            if (item.chain_kind, item.stage, item.candidate_id, item.snapshot_id) not in known:
                raise ValueError("selected source must match a frozen stage snapshot")
            if self.generation_mode == "current" and item.source_kind != "current":
                raise ValueError("current mode cannot select an unadopted candidate")
        return self


class CandidateAdoptRequest(CandidateContract):
    action: Literal["adopt"]
    candidate_id: Identifier
    expected_candidate_token: Identifier
    expected_attempt_id: Identifier
    expected_current_token: Identifier
    request_id: UUID
    continue_after: bool = False
    connection_id: Identifier | None = None
    instruction: str | None = None
    gitlab_connection_id: str = Field(default="", max_length=64)
    comment: str = Field(default="", max_length=4000)


class CandidateEditRequest(CandidateContract):
    expected_candidate_token: Identifier
    expected_attempt_id: Identifier
    content: str = Field(min_length=1)


class CandidateUiSourceCheckRequest(CandidateContract):
    expected_candidate_token: Identifier
    gitlab_connection_id: str = Field(default="", max_length=64)


class CandidateRelationsRunRequest(CandidateContract):
    current_token: Identifier
    connection_id: Identifier
    request_id: UUID


class CandidateRelationsRunResult(CandidateContract):
    attempt_id: Identifier
    replayed: bool


class CandidateRelationsView(CandidateContract):
    candidate_id: Identifier
    snapshot_id: Identifier
    current_token: Identifier
    source_attempt_id: Identifier | None = None
    result_yaml: str
    status: str
    attempt_id: Identifier | None = None
    error_message: str = ""
    case_relations: dict[str, JsonValue] | None = None


class CandidateDeriveRequest(CandidateEditRequest):
    request_id: UUID


class CandidateRevisionRequest(CandidateContract):
    expected_candidate_token: Identifier
    expected_attempt_id: Identifier
    connection_id: Identifier
    instruction: str = Field(min_length=1, max_length=10000)
    request_id: UUID
    attachment_file_ids: list[Identifier] = Field(default_factory=list, max_length=6)
    gitlab_connection_id: str = Field(default="", max_length=64)

    @model_validator(mode="after")
    def validate_revision(self) -> CandidateRevisionRequest:
        if not self.instruction.strip() or len(set(self.attachment_file_ids)) != len(
            self.attachment_file_ids
        ):
            raise ValueError("revision instruction and attachment identities must be valid")
        return self


class CandidateDeriveResult(CandidateContract):
    request_id: UUID
    candidate_id: Identifier
    candidate_token: Identifier
    snapshot_id: Identifier


class CandidateDispositionRequest(CandidateContract):
    action: Literal["reject", "delete"]
    expected_candidate_token: Identifier
    request_id: UUID
    comment: str = Field(default="", max_length=4000)


class CandidateDispositionResult(CandidateContract):
    request_id: UUID
    candidate_id: Identifier
    disposition: Literal["rejected", "deleted"]
    candidate_token: Identifier | None = None


class CurrentClearRequest(CandidateContract):
    expected_current_token: Identifier
    request_id: UUID


class CurrentImportRequest(CandidateContract):
    expected_current_token: Identifier
    expected_lineage_hash: str = Field(min_length=1, max_length=128)
    preview_token: str = Field(min_length=1, max_length=512)
    request_id: UUID
    target_id: str = Field(default="", max_length=64)
    confirm_overwrite: bool = False


class CandidateChainInitializeRequest(CandidateContract):
    task_id: Identifier


class CandidateChainInitializeResult(CandidateContract):
    chain_id: Identifier
    task_id: Identifier
    created: bool


class CandidateRunResult(CandidateContract):
    request_id: UUID
    attempt_id: Identifier
    replayed: bool


class CurrentStageView(CandidateContract):
    stage: Identifier
    current_token: Identifier
    candidate_id: Identifier | None = None
    source_attempt_id: Identifier | None = None
    content: str | None = None
    format: str | None = None
    invalidated_at: datetime | None = None
    invalidated_reason: str | None = None
    active: bool = False
    source_inputs: ChainSourceInputsView | None = None
    material_content: str | None = None
    source_trace: list[CandidateSourceTraceView] = Field(default_factory=list)
    basis_sources: list[CandidateBasisSourceView] = Field(default_factory=list)


class CandidateAdoptResult(CandidateContract):
    request_id: UUID
    candidate_id: Identifier
    content_token: Identifier
    replayed: bool
    continuation_attempt_id: str | None = None
    continuation_error: str = ""


class CurrentClearResult(CandidateContract):
    request_id: UUID
    content_token: Identifier
    replayed: bool


class CurrentImportPreviewRequest(CandidateContract):
    expected_current_token: Identifier
    target_id: str = Field(default="", max_length=64)


class CurrentImportPreviewResult(CandidateContract):
    current_token: Identifier
    full_lineage_hash: str
    content_hash: str
    basis_hash: str
    candidate_id: Identifier
    target_id: str
    preview_token: str
    preview_expires_at: int
    requires_confirmation: bool
    conflicts: list[dict[str, JsonValue]]


class CurrentImportResult(CandidateContract):
    imported: bool
    replayed: bool
    requires_confirmation: bool = False
    conflicts: list[dict[str, JsonValue]] = Field(default_factory=list)
    import_records: list[dict[str, JsonValue]] = Field(default_factory=list)
    changed_case_ids: list[str] = Field(default_factory=list)


class AdoptionBlock(CandidateContract):
    chain_kind: ChainKind
    stage: Identifier
    reason: AdoptionBlockReason


class AdoptionCheck(CandidateContract):
    can_adopt: bool
    lineage_hash: str = Field(min_length=1, max_length=128)
    blocking_sources: list[AdoptionBlock] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result(self) -> AdoptionCheck:
        if self.can_adopt == bool(self.blocking_sources):
            raise ValueError("canAdopt must be false exactly when blocking sources exist")
        return self
