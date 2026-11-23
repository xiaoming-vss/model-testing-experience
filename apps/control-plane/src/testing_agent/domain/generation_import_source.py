"""Immutable, verified current source for a formal import transaction."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from testing_agent.schemas.requirement_design import DesignKind


@dataclass(frozen=True)
class CurrentImportSource:
    requirement_id: str
    chain_id: str
    kind: DesignKind
    stage: str
    stage_id: str
    task_id: str
    candidate_id: str
    snapshot_id: str
    source_attempt_id: str | None
    content_token: str
    content: str
    format: str
    context: dict[str, Any] | None
    source_manifest: dict[str, Any]
    source_snapshot: dict[str, Any]
    upstream_outputs: tuple[dict[str, Any], ...]
    content_hash: str
    basis_hash: str
    source_lineage_hash: str
    full_lineage_hash: str
    confirmed_by: str | None
    confirmed_at: datetime | None
    review_comment: str | None
