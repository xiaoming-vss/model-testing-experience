"""Candidate input metadata from the control-plane worker snapshot.

The worker receives frozen content and never resolves or adopts source IDs.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

Identifier = Annotated[str, Field(min_length=1, max_length=64)]


class FrozenCandidateSource(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    requirement_id: Identifier
    chain_kind: Literal["requirement_analysis", "function", "api", "ui"]
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


class FrozenRootSource(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    snapshot_id: Identifier
    resource_kind: Identifier
    resource_id: Identifier
    content_hash: str = Field(min_length=1, max_length=128)
    source_batch_id: Identifier | None = None


class FrozenSelectedSource(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    chain_kind: Literal["requirement_analysis", "function", "api", "ui"]
    stage: Identifier
    source_kind: Literal["current", "candidate"]
    candidate_id: Identifier
    snapshot_id: Identifier


class FrozenCandidateInput(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

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
