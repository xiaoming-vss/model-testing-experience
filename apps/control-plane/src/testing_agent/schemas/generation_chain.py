"""HTTP contracts for the requirement generation chain workspace."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from testing_agent.schemas.module_generation import ModuleGenerationView
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
    profile_candidate_id: str = ""
    resolved_at: datetime | str | None = None


class ChainSourceInputsView(ChainModel):
    source_kind: Literal["repository"] = "repository"
    repository: ChainSourceRepositoryView
    # Formal functional cases are free-form imported content and stay untyped here.
    cases: list[Any] = Field(default_factory=list)
    source_batch_id: str = ""


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


class UiSourceCurrentProfile(ChainModel):
    candidate_id: str
    label: str = ""
    source_run_id: str = ""
    created_at: datetime | str | None = None
    overall_summary: str = ""
    repositories: list[UiSourceRepositoryOption] = Field(default_factory=list)
    default_repository_id: str = ""


class UiGenerationSourceOptions(ChainModel):
    current_profile: UiSourceCurrentProfile | None = None
    default_repository_id: str = ""


class UiGenerationSourceCheckRequest(ChainModel):
    profile_candidate_id: str = Field(min_length=1, max_length=64)
    repository_id: str = Field(min_length=1, max_length=64)
    pinned_commit: str = Field(min_length=1, max_length=128)
    gitlab_connection_id: str = Field(default="", max_length=64)


class UiGenerationSourceCheck(ChainModel):
    repository_id: str
    branch: str
    pinned_commit: str
    current_commit: str
    changed: bool


class ChainStageView(ChainModel):
    stage: str
    label: str
    order: int
    state: ChainStageState
    upstream_stages: list[str] = Field(default_factory=list)
    blocked_reason: str = ""
    error_message: str = ""
    failure_run_id: str = ""
    failed_at: datetime | str | None = None
    active_run_id: str = ""
    module_generation: ModuleGenerationView | None = None


class GenerationChainView(ChainModel):
    kind: DesignKind
    label: str
    configured: bool
    candidate_mode: bool = False
    task_id: str = ""
    run_id: str = ""
    source_batch_id: str = ""
    active: bool = False
    busy: bool = False
    source_inputs: ChainSourceInputsView | None = None
    source_changed: bool = False
    updated_at: datetime | str | None = None
    pending_candidate_count: int = 0
    continuation_error: str = ""
    stages: list[ChainStageView] = Field(default_factory=list)


class GenerationChainOverview(ChainModel):
    chains: list[GenerationChainView]
