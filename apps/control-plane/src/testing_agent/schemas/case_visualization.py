"""Strict browser contract for entry visualization and batch submission."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator
from pydantic.alias_generators import to_camel


class VisualizationModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class VisualizationRequest(VisualizationModel):
    request_id: str = Field(min_length=1, max_length=64)
    connection_id: str = Field(min_length=1, max_length=64)
    mode: Literal["generate", "regenerate"] = "generate"


class VisualizationLookup(VisualizationModel):
    entry_ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator("entry_ids")
    @classmethod
    def ids(cls, values: list[str]) -> list[str]:
        if any(not v.strip() or len(v) > 64 for v in values):
            raise ValueError("执行条目标识无效")
        return list(dict.fromkeys(values))


class VisualizationBatchRequest(VisualizationLookup):
    request_id: str = Field(min_length=1, max_length=64)
    connection_id: str = Field(min_length=1, max_length=64)


class VisualizationRun(VisualizationModel):
    run_id: str | None = None
    status: str
    artifact_status: Literal["ready", "partial", "unsupported"] | None = None
    error_message: str | None = None


class VisualizationArtifact(VisualizationModel):
    artifact_id: str
    run_id: str | None = None
    schema_version: str
    status: Literal["ready", "partial"]
    content: dict[str, JsonValue] | None = None


class VisualizationResponse(VisualizationModel):
    execution_entry_id: str
    snapshot_hash: str | None = None
    effective_artifact: VisualizationArtifact | None = None
    latest_run: VisualizationRun | None = None
    unavailable_reason: str | None = None


class VisualizationReceipt(VisualizationModel):
    entry_id: str
    disposition: Literal["queued", "existing_active", "skipped_available", "rejected"]
    run_id: str | None = None
    error_message: str | None = None
    run: VisualizationRun | None = None


class VisualizationBatchResponse(VisualizationModel):
    batch_id: str
    items: list[VisualizationReceipt]
    total: int
    counts: dict[str, int]
