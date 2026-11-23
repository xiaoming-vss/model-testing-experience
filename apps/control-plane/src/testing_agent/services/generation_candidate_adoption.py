"""Internal atomic adoption and preflight for authorized candidate operations."""

# transaction-bound: candidate, ancestor slots and target slot are locked together.

from dataclasses import dataclass
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.generation_source_closure import RootKey, SourceClosureError
from testing_agent.models.generation_candidates import AiGenerationCandidate
from testing_agent.repositories.generation_candidate_storage import (
    candidate_stage_scope,
    lock_stage_content,
    replace_current_if_unchanged,
)
from testing_agent.schemas.generation_candidates import (
    AdoptionBlock,
    AdoptionCheck,
    CandidateAdoptRequest,
    ChainKind,
)
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_source_resolution import (
    ResolvedCandidateSelection,
    lock_candidate_source_closure,
)


@dataclass(frozen=True)
class VerifiedAdoption:
    stage_id: str
    check: AdoptionCheck


async def inspect_candidate_adoption(
    session: AsyncSession,
    *,
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    request: CandidateAdoptRequest,
    current_root_hashes: dict[RootKey, str],
    freeze_sources: bool = False,
) -> VerifiedAdoption:
    """Check the candidate and target slot without updating current content.

    Caller must authorize and lock the requirement's parents and bound tasks,
    derive root fingerprints from actual locked business inputs, and own the
    transaction. Preview callers use the default non-freezing mode and rollback.
    Adoption callers freeze sources until their atomic update is committed.
    """
    scope = await candidate_stage_scope(
        session, requirement_id=requirement_id, kind=kind, stage=stage
    )
    if scope is None:
        raise SourceClosureError("source_unknown")
    chain_id, stage_id, _ = scope
    row = (
        await session.execute(
            select(
                AiGenerationCandidate.snapshot_id, AiGenerationCandidate.current_attempt_id
            ).where(
                AiGenerationCandidate.candidate_id == request.candidate_id,
                AiGenerationCandidate.chain_id == chain_id,
                AiGenerationCandidate.stage_id == stage_id,
            )
        )
    ).one_or_none()
    if row is None:
        raise SourceClosureError("source_unknown")
    if row[1] != request.expected_attempt_id:
        raise SourceClosureError("concurrent_change")
    closure = await lock_candidate_source_closure(
        session,
        requirement_id=requirement_id,
        selections=(
            ResolvedCandidateSelection(
                kind,
                stage,
                request.candidate_id,
                row[0],
                request.expected_candidate_token,
            ),
        ),
        required_stages=frozenset({(kind, stage)}),
        current_root_hashes=current_root_hashes,
        freeze_sources=freeze_sources,
    )
    target = await session.scalar(
        select(AiGenerationCandidate)
        .where(
            AiGenerationCandidate.candidate_id == request.candidate_id,
            AiGenerationCandidate.chain_id == chain_id,
            AiGenerationCandidate.stage_id == stage_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    slot = await lock_stage_content(session, chain_id=chain_id, stage_id=stage_id)
    blocks: dict[tuple[str, str], Literal["concurrent_change"]] = {}
    if (
        target is None
        or target.current_attempt_id != request.expected_attempt_id
        or slot is None
        or slot.chain_id != chain_id
        or slot.stage != stage
        or slot.content_token != request.expected_current_token
    ):
        blocks[(kind, stage)] = "concurrent_change"
    result = [
        AdoptionBlock(chain_kind=cast(ChainKind, key[0]), stage=key[1], reason=blocks[key])
        for key in sorted(blocks)
    ]
    return VerifiedAdoption(
        stage_id,
        AdoptionCheck(
            can_adopt=not result, lineage_hash=closure.lineage_hash, blocking_sources=result
        ),
    )


async def adopt_verified_candidate(
    session: AsyncSession,
    *,
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    request: CandidateAdoptRequest,
    actor_id: str,
    current_root_hashes: dict[RootKey, str],
) -> str:
    """Atomically adopt a candidate into its own stage slot."""
    verified = await inspect_candidate_adoption(
        session,
        requirement_id=requirement_id,
        kind=kind,
        stage=stage,
        request=request,
        current_root_hashes=current_root_hashes,
        freeze_sources=True,
    )
    if verified.check.blocking_sources:
        raise SourceClosureError(verified.check.blocking_sources[0].reason)
    token = await replace_current_if_unchanged(
        session,
        stage_id=verified.stage_id,
        expected_content_token=request.expected_current_token,
        candidate_id=request.candidate_id,
        expected_candidate_token=request.expected_candidate_token,
        actor_id=actor_id,
        comment=request.comment,
    )
    if token is None:
        raise SourceClosureError("concurrent_change")
    return token
