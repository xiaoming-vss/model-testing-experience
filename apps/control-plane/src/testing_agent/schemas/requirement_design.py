"""Requirement-scoped generation configuration; legacy task endpoints remain valid."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

DesignKind = Literal["requirement_analysis", "function", "api", "ui"]


class DesignModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class RequirementDesignConfigurationRequest(DesignModel):
    task_id: str | None = Field(default=None, min_length=1, max_length=64)
    new_configuration: bool = False
    request_id: UUID | None = None
    source_content: str | None = None
    instruction: str | None = None


class RequirementDesignRunRequest(DesignModel):
    task_id: str = Field(min_length=1, max_length=64)
    request_id: UUID
    connection_id: str = Field(min_length=1, max_length=64)
    checkpoint_enabled: bool = False
    instruction: str | None = None


class RequirementDesignTaskSummary(DesignModel):
    task_id: str
    kind: DesignKind
    name: str
    source_type: str
    has_source: bool
    source_filename: str
    created_at: datetime | str | None
    updated_at: datetime | str | None


class RequirementDesignResponse(DesignModel):
    tasks: list[RequirementDesignTaskSummary]
    run_counts: dict[str, int]
    active_task_ids: list[str] = Field(default_factory=list)
    adopted_understanding: bool
