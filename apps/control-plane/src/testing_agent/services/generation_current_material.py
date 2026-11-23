"""Resolve the adopted material and its actual source for auxiliary work."""

# transaction-bound: candidate, document and current slot must stay locked together.

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.generation_content_hash import generation_content_hash
from testing_agent.domain.generation_source_closure import RootSnapshot, SourceClosureError
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
)
from testing_agent.repositories.generation_candidate_storage import (
    candidate_stage_scope,
    lock_stage_content,
)
from testing_agent.services.generation_source_resolution import (
    ResolvedCandidateSelection,
    lock_candidate_source_closure,
    read_closure_candidates,
)


@dataclass(frozen=True)
class CurrentMaterial:
    """A server-verified material input, suitable for later equality rechecks."""

    candidate_id: str
    snapshot_id: str
    candidate_token: str
    current_token: str
    task_id: str
    attempt_id: str | None
    content: str
    content_hash: str
    basis_hash: str
    lineage_hash: str
    document_root_hash: str


async def lock_current_material(
    session: AsyncSession,
    *,
    requirement_id: str,
    document_root: RootSnapshot,
    freeze: bool,
    expected: CurrentMaterial | None = None,
) -> CurrentMaterial:
    """Recheck the current slot and frozen graph under caller-owned parent locks.

    The caller must authorize the actor, lock the requirement and its tasks,
    and calculate ``document_root`` from the actual prepared document in this
    transaction. Preparation must happen outside the business locks. Preflight
    may use ``freeze=False`` and release the transaction; a real dispatch must
    call again with ``freeze=True`` and its preflight value as ``expected``.
    """
    if (
        document_root.resource_kind != "requirement_document"
        or document_root.resource_id != requirement_id
    ):
        raise SourceClosureError("source_unknown")
    scope = await candidate_stage_scope(
        session, requirement_id=requirement_id, kind="requirement_analysis", stage="extracting_text"
    )
    if scope is None:
        raise SourceClosureError("pending_upstream")
    chain_id, stage_id, task = scope
    row = (
        await session.execute(
            select(
                AiGenerationStageContent.content_token,
                AiGenerationCandidate.candidate_id,
                AiGenerationCandidate.snapshot_id,
                AiGenerationCandidate.candidate_token,
            )
            .join(
                AiGenerationCandidate,
                AiGenerationCandidate.candidate_id == AiGenerationStageContent.source_candidate_id,
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
    current_token, candidate_id, snapshot_id, candidate_token = row
    closure = await lock_candidate_source_closure(
        session,
        requirement_id=requirement_id,
        selections=(
            ResolvedCandidateSelection(
                "requirement_analysis",
                "extracting_text",
                candidate_id,
                snapshot_id,
                candidate_token,
            ),
        ),
        required_stages=frozenset({("requirement_analysis", "extracting_text")}),
        current_root_hashes={document_root.key: document_root.content_hash},
        freeze_sources=freeze,
    )
    candidates = await read_closure_candidates(session, closure)
    slot = await lock_stage_content(session, chain_id=chain_id, stage_id=stage_id)
    if (
        slot is None
        or slot.content_token != current_token
        or slot.source_candidate_id != candidate_id
    ):
        raise SourceClosureError("concurrent_change")
    if slot.invalidated_at is not None:
        raise SourceClosureError("source_stale")
    if slot.content is None or slot.format is None:
        raise SourceClosureError("source_stale")
    candidate = candidates[candidate_id]
    node = next(item for item in closure.stages if item.candidate_id == candidate_id)
    try:
        slot_content_hash = generation_content_hash(slot.content, slot.format)
    except (TypeError, ValueError) as exc:
        raise SourceClosureError("source_stale") from exc
    if (
        slot_content_hash != slot.content_hash
        or slot.content_hash != node.content_hash
        or slot.basis_hash != node.basis_hash
        or slot.lineage_hash != candidate.lineage_hash
    ):
        raise SourceClosureError("source_stale")
    material = CurrentMaterial(
        candidate_id=candidate_id,
        snapshot_id=snapshot_id,
        candidate_token=candidate_token,
        current_token=current_token,
        task_id=task.task_id,
        attempt_id=candidate.current_attempt_id,
        content=candidate.content,
        content_hash=node.content_hash,
        basis_hash=node.basis_hash,
        lineage_hash=closure.lineage_hash,
        document_root_hash=document_root.content_hash,
    )
    if expected is not None and material != expected:
        raise SourceClosureError("concurrent_change")
    return material
