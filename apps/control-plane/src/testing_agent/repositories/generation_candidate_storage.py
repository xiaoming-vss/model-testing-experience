"""Transaction-scoped storage primitives; not an adoption or authorization API.

Callers must lock and validate the complete source graph before using these
operations. They deliberately do not commit or create an audit receipt. The
public workflow must provide those guarantees before it can call this module.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.ai_tasks import task_type_for
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
    RequirementGenerationChain,
)
from testing_agent.repositories.requirement_design import requirement_scope
from testing_agent.schemas.requirement_design import DesignKind


@dataclass(frozen=True)
class CandidateEditSnapshot:
    """Validated result of an already persisted manual-edit attempt.

    The service must check the attempt belongs to the candidate's stage and
    calculate the content fingerprint before calling this storage primitive.
    """

    attempt_id: str
    content: str
    format: str
    context_json: dict[str, Any] | None
    content_hash: str


@dataclass(frozen=True)
class CandidateSummary:
    candidate_id: str
    snapshot_id: str
    candidate_token: str
    current_attempt_id: str | None
    derived_from_candidate_id: str | None
    disposition: str
    generation_mode: str
    frozen_at: datetime | None
    created_by: str
    created_at: datetime
    is_current: bool


async def candidate_stage_scope(
    session: AsyncSession, *, requirement_id: str, kind: DesignKind, stage: str
) -> tuple[str, str, AiGenerateTask] | None:
    """Resolve the stage only when its task, chain and requirement agree."""
    row = (
        await session.execute(
            select(RequirementGenerationChain.chain_id, AiGenerationStage.id, AiGenerateTask)
            .join(AiGenerateTask, AiGenerateTask.task_id == RequirementGenerationChain.task_id)
            .join(AiGenerationStage, AiGenerationStage.task_id == AiGenerateTask.task_id)
            .where(
                RequirementGenerationChain.requirement_id == requirement_id,
                RequirementGenerationChain.kind == kind,
                AiGenerateTask.task_type == task_type_for(kind),
                AiGenerationStage.stage == stage,
                *requirement_scope(requirement_id),
            )
        )
    ).one_or_none()
    return (row[0], row[1], row[2]) if row is not None else None


async def current_source_candidate_id(
    session: AsyncSession, *, chain_id: str, stage_id: str
) -> str | None:
    return await session.scalar(
        select(AiGenerationStageContent.source_candidate_id).where(
            AiGenerationStageContent.chain_id == chain_id,
            AiGenerationStageContent.stage_id == stage_id,
        )
    )


async def read_current_stage(
    session: AsyncSession, *, chain_id: str, stage_id: str
) -> tuple[AiGenerationStageContent, bool] | None:
    """Read one current slot and whether its stage is running."""
    row = (
        await session.execute(
            select(AiGenerationStageContent, AiGenerationStage.active_attempt_id)
            .join(AiGenerationStage, AiGenerationStage.id == AiGenerationStageContent.stage_id)
            .where(
                AiGenerationStageContent.chain_id == chain_id,
                AiGenerationStageContent.stage_id == stage_id,
            )
        )
    ).one_or_none()
    return (row[0], bool(row[1])) if row else None


async def list_candidate_summaries(
    session: AsyncSession, *, chain_id: str, stage_id: str, page: int, page_size: int
) -> tuple[list[CandidateSummary], int]:
    """Return bounded metadata only; caller must authorize chain and stage scope."""
    if page < 1 or not 1 <= page_size <= 100:
        raise ValueError("invalid candidate pagination")
    candidate = AiGenerationCandidate
    slot = AiGenerationStageContent
    conditions = (candidate.chain_id == chain_id, candidate.stage_id == stage_id)
    total = await session.scalar(select(func.count()).select_from(candidate).where(*conditions))
    rows = (
        await session.execute(
            select(
                candidate.candidate_id,
                candidate.snapshot_id,
                candidate.candidate_token,
                candidate.current_attempt_id,
                candidate.derived_from_candidate_id,
                candidate.disposition,
                candidate.generation_mode,
                candidate.frozen_at,
                candidate.created_by,
                candidate.created_at,
                (slot.source_candidate_id == candidate.candidate_id).label("is_current"),
            )
            .outerjoin(
                slot, (slot.stage_id == candidate.stage_id) & (slot.chain_id == candidate.chain_id)
            )
            .where(*conditions)
            .order_by(candidate.created_at.desc(), candidate.candidate_id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return [
        CandidateSummary(
            candidate_id=row.candidate_id,
            snapshot_id=row.snapshot_id,
            candidate_token=row.candidate_token,
            current_attempt_id=row.current_attempt_id,
            derived_from_candidate_id=row.derived_from_candidate_id,
            disposition=row.disposition,
            generation_mode=row.generation_mode,
            frozen_at=row.frozen_at,
            created_by=row.created_by,
            created_at=row.created_at,
            is_current=bool(row.is_current),
        )
        for row in rows
    ], total or 0


async def get_stage_candidate(
    session: AsyncSession, *, chain_id: str, stage_id: str, candidate_id: str
) -> AiGenerationCandidate | None:
    """Read the full candidate snapshot after the caller authorizes its scope."""
    return await session.scalar(
        select(AiGenerationCandidate)
        .where(
            AiGenerationCandidate.chain_id == chain_id,
            AiGenerationCandidate.stage_id == stage_id,
            AiGenerationCandidate.candidate_id == candidate_id,
        )
        .execution_options(populate_existing=True)
    )


async def freeze_candidate_for_reference(
    session: AsyncSession,
    *,
    chain_id: str,
    stage_id: str,
    candidate_id: str,
    expected_candidate_token: str,
    expected_snapshot_id: str,
) -> AiGenerationCandidate | None:
    """Lock a selected candidate and make its snapshot immutable in this transaction.

    Callers validate access and the complete source graph and persist the
    dependent attempt before committing. A rollback also rolls back the freeze.
    """
    candidate = await session.scalar(
        select(AiGenerationCandidate)
        .where(
            AiGenerationCandidate.candidate_id == candidate_id,
            AiGenerationCandidate.chain_id == chain_id,
            AiGenerationCandidate.stage_id == stage_id,
            AiGenerationCandidate.candidate_token == expected_candidate_token,
            AiGenerationCandidate.snapshot_id == expected_snapshot_id,
            AiGenerationCandidate.disposition == "available",
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if candidate is None:
        return None
    if candidate.frozen_at is None:
        candidate.frozen_at = datetime.now(UTC)
        await session.flush()
    return candidate


async def edit_unfrozen_candidate_if_unchanged(
    session: AsyncSession,
    *,
    chain_id: str,
    stage_id: str,
    candidate_id: str,
    expected_candidate_token: str,
    expected_attempt_id: str,
    replacement: CandidateEditSnapshot,
) -> tuple[str, str] | None:
    """Atomically replace an unreferenced candidate's snapshot, without committing.

    The caller must authorize the operation and validate the new edit attempt.
    Once selected for reference or adopted, the candidate cannot be edited here.
    """
    token, snapshot_id = uuid4().hex, uuid4().hex
    result = await session.execute(
        update(AiGenerationCandidate)
        .where(
            AiGenerationCandidate.candidate_id == candidate_id,
            AiGenerationCandidate.chain_id == chain_id,
            AiGenerationCandidate.stage_id == stage_id,
            AiGenerationCandidate.candidate_token == expected_candidate_token,
            AiGenerationCandidate.current_attempt_id == expected_attempt_id,
            AiGenerationCandidate.disposition == "available",
            AiGenerationCandidate.frozen_at.is_(None),
        )
        .values(
            current_attempt_id=replacement.attempt_id,
            snapshot_id=snapshot_id,
            candidate_token=token,
            content=replacement.content,
            format=replacement.format,
            context_json=replacement.context_json,
            content_hash=replacement.content_hash,
        )
    )
    if cast(CursorResult[Any], result).rowcount != 1:
        return None
    return token, snapshot_id


async def dispose_candidate_if_unchanged(
    session: AsyncSession,
    *,
    chain_id: str,
    stage_id: str,
    candidate_id: str,
    expected_candidate_token: str,
    disposition: Literal["rejected", "discarded"],
) -> str | None:
    """Reject or discard one available candidate, unless it is current.

    Authorization, audit receipts and propagation to descendants are service
    responsibilities. The candidate and slot use the same lock order as the
    current-content replacement primitive.
    """
    candidate = await session.scalar(
        select(AiGenerationCandidate)
        .where(
            AiGenerationCandidate.candidate_id == candidate_id,
            AiGenerationCandidate.chain_id == chain_id,
            AiGenerationCandidate.stage_id == stage_id,
            AiGenerationCandidate.candidate_token == expected_candidate_token,
            AiGenerationCandidate.disposition == "available",
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if candidate is None:
        return None
    current = await session.scalar(
        select(AiGenerationStageContent)
        .where(
            AiGenerationStageContent.stage_id == stage_id,
            AiGenerationStageContent.chain_id == chain_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if current is None or current.source_candidate_id == candidate_id:
        return None
    token = uuid4().hex
    candidate.disposition = disposition
    candidate.candidate_token = token
    await session.flush()
    return token


async def lock_stage_content(
    session: AsyncSession, *, chain_id: str, stage_id: str
) -> AiGenerationStageContent | None:
    """Lock one stage slot for caller-owned validation and update."""
    return await session.scalar(
        select(AiGenerationStageContent)
        .where(
            AiGenerationStageContent.chain_id == chain_id,
            AiGenerationStageContent.stage_id == stage_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def replace_current_if_unchanged(
    session: AsyncSession,
    *,
    stage_id: str,
    expected_content_token: str,
    candidate_id: str,
    expected_candidate_token: str,
    actor_id: str,
    comment: str,
) -> str | None:
    """Copy one locked candidate into its stage slot using compare-and-swap.

    A return of None means the candidate/slot changed or is unavailable. This
    only enforces local storage invariants, not upstream or root-source validity.
    """
    candidate = await session.scalar(
        select(AiGenerationCandidate)
        .where(
            AiGenerationCandidate.candidate_id == candidate_id,
            AiGenerationCandidate.stage_id == stage_id,
            AiGenerationCandidate.candidate_token == expected_candidate_token,
            AiGenerationCandidate.disposition == "available",
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if candidate is None:
        return None
    token = uuid4().hex
    result = await session.execute(
        update(AiGenerationStageContent)
        .where(
            AiGenerationStageContent.stage_id == stage_id,
            AiGenerationStageContent.chain_id == candidate.chain_id,
            AiGenerationStageContent.content_token == expected_content_token,
        )
        .values(
            content=candidate.content,
            format=candidate.format,
            context_json=candidate.context_json,
            content_hash=candidate.content_hash,
            basis_hash=candidate.basis_hash,
            content_token=token,
            source_manifest_json=candidate.source_manifest_json,
            source_snapshot_json=candidate.source_snapshot_json,
            lineage_hash=candidate.lineage_hash,
            source_attempt_id=candidate.current_attempt_id,
            source_candidate_id=candidate.candidate_id,
            confirmed_by=actor_id,
            confirmed_at=datetime.now(UTC),
            comment=comment,
            invalidated_at=None,
            invalidated_reason=None,
        )
    )
    if cast(CursorResult[Any], result).rowcount != 1:
        return None
    if candidate.frozen_at is None:
        candidate.frozen_at = datetime.now(UTC)
        await session.flush()
    return token


async def clear_current_if_unchanged(
    session: AsyncSession, *, stage_id: str, expected_content_token: str
) -> str | None:
    """Clear the slot without deleting its identity or reusing its old token."""
    token = uuid4().hex
    result = await session.execute(
        update(AiGenerationStageContent)
        .where(
            AiGenerationStageContent.stage_id == stage_id,
            AiGenerationStageContent.content_token == expected_content_token,
        )
        .values(
            content=None,
            format=None,
            context_json=None,
            content_hash=None,
            basis_hash=None,
            content_token=token,
            source_manifest_json=None,
            source_snapshot_json=None,
            lineage_hash=None,
            source_attempt_id=None,
            source_candidate_id=None,
            confirmed_by=None,
            confirmed_at=None,
            comment=None,
            invalidated_at=None,
            invalidated_reason=None,
        )
    )
    return token if cast(CursorResult[Any], result).rowcount == 1 else None
