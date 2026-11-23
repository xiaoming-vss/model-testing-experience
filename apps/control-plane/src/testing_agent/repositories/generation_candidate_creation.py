"""Persist successful attempt outputs as independently retained candidates."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.generation_content_hash import generation_content_hash
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.generation_candidates import AiGenerationCandidate
from testing_agent.repositories.generation_current_chain import ensure_empty_slot


class CandidateCreationConflict(ValueError):
    """The successful attempt or its frozen provenance is inconsistent."""


@dataclass(frozen=True)
class CandidateProvenance:
    """Server-resolved sources, or explicit unknowns; never use client graphs."""

    generation_mode: Literal["current", "trial"]
    source_manifest: dict[str, Any] | None
    lineage_hash: str | None
    basis_hash: str | None
    derived_from_candidate_id: str | None = None


async def create_candidate_from_successful_attempt(
    session: AsyncSession,
    *,
    chain_id: str,
    stage_id: str,
    attempt_id: str,
    provenance: CandidateProvenance,
) -> AiGenerationCandidate:
    """Copy a successful output exactly once within the caller's transaction.

    The caller must have authorized the action, locked the project, sprint and
    task, and validated and locked the complete source graph. Replaying a
    completed attempt never rewrites an already edited or adopted candidate.
    """
    stage = await session.scalar(
        select(AiGenerationStage)
        .where(AiGenerationStage.id == stage_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if stage is None:
        raise CandidateCreationConflict("stage not found")
    attempt = await session.scalar(
        select(AiGenerationAttempt)
        .where(AiGenerationAttempt.id == attempt_id, AiGenerationAttempt.stage_id == stage_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        attempt is None
        or attempt.status != "success"
        or not attempt.output_content
        or not attempt.output_content.strip()
        or not attempt.output_format
        or not attempt.requested_by
        or provenance.generation_mode not in {"current", "trial"}
        or (
            provenance.source_manifest is not None
            and not isinstance(provenance.source_manifest, dict)
        )
        or provenance.lineage_hash == ""
        or provenance.basis_hash == ""
    ):
        raise CandidateCreationConflict("attempt or provenance is incomplete")
    try:
        content_hash = generation_content_hash(attempt.output_content, attempt.output_format)
    except ValueError as exc:
        raise CandidateCreationConflict("attempt output cannot be fingerprinted") from exc
    await ensure_empty_slot(session, chain_id=chain_id, stage_id=stage_id)
    existing = await session.scalar(
        select(AiGenerationCandidate)
        .where(
            AiGenerationCandidate.stage_id == stage_id,
            AiGenerationCandidate.origin_attempt_id == attempt_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if existing is not None:
        if (
            existing.chain_id != chain_id
            or existing.generation_mode != provenance.generation_mode
            or existing.source_manifest_json != provenance.source_manifest
            or existing.lineage_hash != provenance.lineage_hash
            or existing.basis_hash != provenance.basis_hash
            or existing.derived_from_candidate_id != provenance.derived_from_candidate_id
        ):
            raise CandidateCreationConflict("attempt already has different provenance")
        return existing
    if provenance.derived_from_candidate_id:
        parent = await session.scalar(
            select(AiGenerationCandidate)
            .where(
                AiGenerationCandidate.candidate_id == provenance.derived_from_candidate_id,
                AiGenerationCandidate.chain_id == chain_id,
                AiGenerationCandidate.stage_id == stage_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if parent is None:
            raise CandidateCreationConflict("derived candidate has an invalid parent")
        if parent.frozen_at is None:
            parent.frozen_at = datetime.now(UTC)
    candidate = AiGenerationCandidate(
        candidate_id=uuid4().hex,
        snapshot_id=uuid4().hex,
        chain_id=chain_id,
        stage_id=stage_id,
        origin_attempt_id=attempt.id,
        current_attempt_id=attempt.id,
        derived_from_candidate_id=provenance.derived_from_candidate_id,
        content=attempt.output_content,
        format=attempt.output_format,
        context_json=deepcopy(attempt.output_context_json),
        candidate_token=uuid4().hex,
        disposition="available",
        generation_mode=provenance.generation_mode,
        source_manifest_json=deepcopy(provenance.source_manifest),
        source_snapshot_json=deepcopy(attempt.input_snapshot_json),
        lineage_hash=provenance.lineage_hash,
        content_hash=content_hash,
        basis_hash=provenance.basis_hash,
        created_by=attempt.requested_by,
    )
    session.add(candidate)
    await session.flush()
    return candidate
