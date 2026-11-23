"""Read the frozen UI source selected for a downstream candidate run."""

# transaction-bound: callers recheck selected candidate identity under parent locks.

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
)
from testing_agent.repositories.generation_candidate_storage import candidate_stage_scope
from testing_agent.schemas.generation_candidates import CandidateRunRequest


@dataclass(frozen=True)
class SelectedUiSurfaceSource:
    candidate_id: str
    snapshot_id: str
    candidate_token: str
    current_token: str | None
    source: dict[str, Any]


async def read_selected_ui_surface_source(
    session: AsyncSession, *, requirement_id: str, request: CandidateRunRequest
) -> SelectedUiSurfaceSource:
    """Read a scoped server-owned source before verifying its complete ancestry.

    The caller must authorize the requirement. These values are provisional:
    dispatch must recheck the selected identity and validate the full candidate
    closure and formal-case root under locks after any remote GitLab calls.
    """
    scope = await candidate_stage_scope(
        session, requirement_id=requirement_id, kind="ui", stage="ui_surface"
    )
    if scope is None:
        raise SourceClosureError("pending_upstream")
    chain_id, stage_id, _ = scope
    choices = [
        item
        for item in request.source_selections
        if item.chain_kind == "ui" and item.stage == "ui_surface"
    ]
    if request.generation_mode == "trial" and len(choices) != 1:
        raise SourceClosureError("source_unknown")
    choice = choices[0] if choices else None
    current_token: str | None = None
    if choice is not None and choice.source_kind == "candidate":
        candidate = await session.scalar(
            select(AiGenerationCandidate).where(
                AiGenerationCandidate.chain_id == chain_id,
                AiGenerationCandidate.stage_id == stage_id,
                AiGenerationCandidate.candidate_id == choice.candidate_id,
            )
        )
        if candidate is None:
            raise SourceClosureError("source_unknown")
        if (
            candidate.snapshot_id != choice.snapshot_id
            or candidate.candidate_token != choice.expected_candidate_token
        ):
            raise SourceClosureError("concurrent_change")
    else:
        row = (
            await session.execute(
                select(AiGenerationCandidate, AiGenerationStageContent.content_token)
                .join(
                    AiGenerationStageContent,
                    AiGenerationStageContent.source_candidate_id
                    == AiGenerationCandidate.candidate_id,
                )
                .where(
                    AiGenerationStageContent.chain_id == chain_id,
                    AiGenerationStageContent.stage_id == stage_id,
                    AiGenerationCandidate.chain_id == chain_id,
                    AiGenerationCandidate.stage_id == stage_id,
                )
            )
        ).one_or_none()
        if row is None:
            raise SourceClosureError("pending_upstream")
        candidate, current_token = row
        if choice is not None and choice.expected_current_token != current_token:
            raise SourceClosureError("concurrent_change")
    snapshot = candidate.source_snapshot_json
    source = snapshot.get("source") if isinstance(snapshot, dict) else None
    if candidate.disposition != "available":
        raise SourceClosureError("source_stale")
    if not isinstance(source, dict):
        raise SourceClosureError("source_unknown")
    return SelectedUiSurfaceSource(
        candidate_id=candidate.candidate_id,
        snapshot_id=candidate.snapshot_id,
        candidate_token=candidate.candidate_token,
        current_token=current_token,
        source=deepcopy(source),
    )
