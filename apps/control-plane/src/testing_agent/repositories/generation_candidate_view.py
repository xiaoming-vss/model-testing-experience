"""Bounded metadata for the current candidate chain overview."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
    RequirementGenerationChain,
)
from testing_agent.repositories.generation_schema import candidate_schema_installed


@dataclass(frozen=True)
class CandidateStageStatus:
    stage: str
    active_attempt_id: str | None
    candidate_count: int
    current_candidate_id: str | None
    invalidated_at: datetime | None
    last_status: str | None
    last_error: str | None
    last_attempt_id: str | None
    last_attempt_at: datetime | None
    confirmed_at: datetime | None
    module_attempt: Any | None


async def has_adopted_material(session: AsyncSession, requirement_id: str) -> bool:
    return (
        await session.scalar(
            select(AiGenerationStageContent.stage_id)
            .join(
                RequirementGenerationChain,
                RequirementGenerationChain.chain_id == AiGenerationStageContent.chain_id,
            )
            .where(
                RequirementGenerationChain.requirement_id == requirement_id,
                RequirementGenerationChain.kind == "requirement_analysis",
                AiGenerationStageContent.stage == "extracting_text",
                AiGenerationStageContent.source_candidate_id.is_not(None),
            )
            .limit(1)
        )
        is not None
    )


async def read_candidate_chain_status(
    session: AsyncSession, *, requirement_id: str, kind: str, task_id: str
) -> list[CandidateStageStatus] | None:
    """Read stage status without loading generated or source bodies."""
    if not await candidate_schema_installed(session):
        return None
    chain_id = await session.scalar(
        select(RequirementGenerationChain.chain_id).where(
            RequirementGenerationChain.requirement_id == requirement_id,
            RequirementGenerationChain.kind == kind,
            RequirementGenerationChain.task_id == task_id,
        )
    )
    if chain_id is None:
        return None
    latest_status = (
        select(AiGenerationAttempt.status)
        .where(AiGenerationAttempt.stage_id == AiGenerationStage.id)
        .order_by(AiGenerationAttempt.attempt_no.desc())
        .limit(1)
        .correlate(AiGenerationStage)
        .scalar_subquery()
    )
    latest_error = (
        select(AiGenerationAttempt.error_message)
        .where(AiGenerationAttempt.stage_id == AiGenerationStage.id)
        .order_by(AiGenerationAttempt.attempt_no.desc())
        .limit(1)
        .correlate(AiGenerationStage)
        .scalar_subquery()
    )
    latest_attempt_id = (
        select(AiGenerationAttempt.id)
        .where(AiGenerationAttempt.stage_id == AiGenerationStage.id)
        .order_by(AiGenerationAttempt.attempt_no.desc())
        .limit(1)
        .correlate(AiGenerationStage)
        .scalar_subquery()
    )
    latest_attempt_at = (
        select(func.coalesce(AiGenerationAttempt.finished_at, AiGenerationAttempt.created_at))
        .where(AiGenerationAttempt.stage_id == AiGenerationStage.id)
        .order_by(AiGenerationAttempt.attempt_no.desc())
        .limit(1)
        .correlate(AiGenerationStage)
        .scalar_subquery()
    )
    rows = (
        await session.execute(
            select(
                AiGenerationStage.stage,
                AiGenerationStage.id,
                AiGenerationStage.active_attempt_id,
                AiGenerationStageContent.source_candidate_id,
                AiGenerationStageContent.invalidated_at,
                AiGenerationStageContent.confirmed_at,
                latest_status.label("last_status"),
                latest_error.label("last_error"),
                latest_attempt_id.label("last_attempt_id"),
                latest_attempt_at.label("last_attempt_at"),
            )
            .outerjoin(
                AiGenerationStageContent,
                (AiGenerationStageContent.stage_id == AiGenerationStage.id)
                & (AiGenerationStageContent.chain_id == chain_id),
            )
            .where(AiGenerationStage.task_id == task_id)
        )
    ).all()
    count_rows = (
        await session.execute(
            select(AiGenerationCandidate.stage_id, func.count())
            .where(
                AiGenerationCandidate.chain_id == chain_id,
                AiGenerationCandidate.disposition == "available",
            )
            .group_by(AiGenerationCandidate.stage_id)
        )
    ).all()
    counts: dict[str, int] = {row[0]: row[1] for row in count_rows}
    progress_ids = [
        row.active_attempt_id or row.last_attempt_id
        for row in rows
        if row.stage in {"case_names", "detailed_cases"}
        and (row.active_attempt_id or row.last_attempt_id)
    ]
    progress = {}
    if progress_ids:
        attempts = (
            await session.execute(
                select(
                    AiGenerationAttempt.id,
                    AiGenerationAttempt.status,
                    AiGenerationAttempt.output_context_json,
                ).where(AiGenerationAttempt.id.in_(progress_ids))
            )
        ).all()
        progress = {attempt.id: attempt for attempt in attempts}
    return [
        CandidateStageStatus(
            row.stage,
            row.active_attempt_id,
            counts.get(row.id, 0),
            row.source_candidate_id,
            row.invalidated_at,
            row.last_status,
            row.last_error,
            row.last_attempt_id,
            row.last_attempt_at,
            row.confirmed_at,
            progress.get(row.active_attempt_id or row.last_attempt_id),
        )
        for row in rows
    ]
