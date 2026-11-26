"""Project-scoped read of adopted material and relation projections."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.generation_chain import HISTORICAL_REQUIREMENT_STAGE
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
    RequirementGenerationChain,
)
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint


@dataclass(frozen=True)
class HistoricalMaterial:
    requirement_id: str
    snapshot_id: str
    functions: str | list[dict[str, Any]] | None


def _adopted(project_id: str, stage: str) -> Select[Any]:
    return (
        select()
        .select_from(AiGenerationStageContent)
        .join(RequirementGenerationChain)
        .join(Requirement, Requirement.requirement_id == RequirementGenerationChain.requirement_id)
        .join(Sprint, Sprint.sprint_id == Requirement.sprint_id)
        .join(
            AiGenerationCandidate,
            AiGenerationCandidate.candidate_id == AiGenerationStageContent.source_candidate_id,
        )
        .where(
            Sprint.project_id == project_id,
            RequirementGenerationChain.kind == "requirement_analysis",
            AiGenerationStageContent.stage == stage,
            AiGenerationStageContent.invalidated_at.is_(None),
            AiGenerationStageContent.format == "json",
            AiGenerationCandidate.disposition == "available",
            AiGenerationCandidate.chain_id == AiGenerationStageContent.chain_id,
            AiGenerationCandidate.stage_id == AiGenerationStageContent.stage_id,
            AiGenerationCandidate.content_hash == AiGenerationStageContent.content_hash,
        )
    )


async def iter_project_materials(
    session: AsyncSession, *, project_id: str, current_requirement_id: str
) -> AsyncIterator[HistoricalMaterial]:
    """Stream selected fields from every eligible iteration, in recency tie-break order."""
    content = AiGenerationStageContent.content
    valid_json = case((func.json_valid(content), content), else_=None)
    stmt = (
        _adopted(project_id, "extracting_text")
        .add_columns(
            Requirement.requirement_id,
            AiGenerationCandidate.snapshot_id,
            func.json_extract(valid_json, "$.functions"),
        )
        .where(Requirement.requirement_id != current_requirement_id)
        .order_by(Sprint.start_time.desc(), Requirement.id.desc())
        .execution_options(yield_per=100)
    )
    rows = await session.stream(stmt)
    try:
        async for requirement_id, snapshot_id, functions in rows:
            yield HistoricalMaterial(requirement_id, snapshot_id, functions)
    finally:
        await rows.close()


async def read_adopted_relation_results(
    session: AsyncSession, *, project_id: str, requirement_ids: set[str]
) -> list[str]:
    """Read adopted relations for the selected requirements in one project."""
    if not requirement_ids:
        return []
    stmt = (
        _adopted(project_id, HISTORICAL_REQUIREMENT_STAGE)
        .add_columns(AiGenerationStageContent.content)
        .where(Requirement.requirement_id.in_(requirement_ids))
        .order_by(Requirement.requirement_id)
    )
    return [content for content in (await session.scalars(stmt)).all() if content is not None]
