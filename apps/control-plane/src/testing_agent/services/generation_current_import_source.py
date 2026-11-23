"""Lock and verify the complete current source before a formal import."""

# transaction-bound: source, candidates and all current slots must stay locked until import.

from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.generation_chain import is_final_stage
from testing_agent.domain.generation_content_hash import generation_content_hash
from testing_agent.domain.generation_import_source import CurrentImportSource
from testing_agent.domain.generation_source_closure import RootKey, SourceClosureError
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
)
from testing_agent.repositories.generation_candidate_storage import (
    candidate_stage_scope,
    lock_stage_content,
)
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_source_resolution import (
    ResolvedCandidateSelection,
    lock_candidate_source_closure,
    read_closure_candidates,
)


async def lock_current_import_source(
    session: AsyncSession,
    *,
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    expected_current_token: str,
    current_root_hashes: dict[RootKey, str],
    expected_lineage_hash: str | None = None,
) -> CurrentImportSource:
    """Verify the selected current leaf and its frozen closure in this transaction.

    The authorized caller locks parent business resources and tasks and computes
    root hashes from real inputs before calling. Preview callers may omit the
    expected lineage; import callers must supply the previously previewed hash
    and keep all locks until the target and receipt are committed. No candidate
    is frozen or changed merely by running this source check.
    """
    if kind not in {"function", "api", "ui"} or not is_final_stage(kind, stage):
        raise SourceClosureError("source_unknown")
    scope = await candidate_stage_scope(
        session, requirement_id=requirement_id, kind=kind, stage=stage
    )
    if scope is None:
        raise SourceClosureError("source_unknown")
    chain_id, stage_id, _ = scope
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
    if row[0] != expected_current_token:
        raise SourceClosureError("concurrent_change")
    closure = await lock_candidate_source_closure(
        session,
        requirement_id=requirement_id,
        selections=(ResolvedCandidateSelection(kind, stage, row[1], row[2], row[3]),),
        required_stages=frozenset({(kind, stage)}),
        current_root_hashes=current_root_hashes,
        freeze_sources=False,
    )
    if expected_lineage_hash is not None and closure.lineage_hash != expected_lineage_hash:
        raise SourceClosureError("concurrent_change")
    candidates = await read_closure_candidates(session, closure)
    slot = await lock_stage_content(session, chain_id=chain_id, stage_id=stage_id)
    if slot is None or slot.content_token != expected_current_token:
        raise SourceClosureError("concurrent_change")
    if slot.invalidated_at is not None:
        raise SourceClosureError("source_stale")
    candidate = candidates[row[1]]
    if (
        candidate.snapshot_id != row[2]
        or not isinstance(slot.source_manifest_json, dict)
        or not isinstance(slot.source_snapshot_json, dict)
        or slot.content is None
        or slot.format is None
        or not slot.content_hash
        or not slot.basis_hash
        or not slot.lineage_hash
    ):
        raise SourceClosureError("source_unknown")
    try:
        slot_content_hash = generation_content_hash(slot.content, slot.format)
    except (TypeError, ValueError) as exc:
        raise SourceClosureError("source_unknown") from exc
    if (
        slot_content_hash != slot.content_hash
        or slot.content_hash != candidate.content_hash
        or slot.basis_hash != candidate.basis_hash
        or slot.lineage_hash != candidate.lineage_hash
    ):
        raise SourceClosureError("source_stale")
    return CurrentImportSource(
        requirement_id=requirement_id,
        chain_id=chain_id,
        kind=kind,
        stage=stage,
        stage_id=stage_id,
        task_id=scope[2].task_id,
        candidate_id=candidate.candidate_id,
        snapshot_id=candidate.snapshot_id,
        source_attempt_id=slot.source_attempt_id,
        content_token=slot.content_token,
        content=slot.content,
        format=slot.format,
        context=deepcopy(slot.context_json),
        source_manifest=deepcopy(slot.source_manifest_json),
        source_snapshot=deepcopy(slot.source_snapshot_json),
        upstream_outputs=tuple(
            {
                "chainKind": node.chain_kind,
                "stage": node.stage,
                "candidateId": node.candidate_id,
                "snapshotId": node.snapshot_id,
                "content": candidates[node.candidate_id].content,
                "format": candidates[node.candidate_id].format,
                "contentHash": node.content_hash,
                "basisHash": node.basis_hash,
                "sourceBatchId": node.source_batch_id,
                "parentSnapshotIds": list(node.parent_snapshot_ids),
                "rootSnapshotIds": list(node.root_snapshot_ids),
            }
            for node in closure.stages
            if node.candidate_id != candidate.candidate_id
        ),
        content_hash=slot.content_hash,
        basis_hash=slot.basis_hash,
        source_lineage_hash=slot.lineage_hash,
        full_lineage_hash=closure.lineage_hash,
        confirmed_by=slot.confirmed_by,
        confirmed_at=slot.confirmed_at,
        review_comment=slot.comment,
    )
