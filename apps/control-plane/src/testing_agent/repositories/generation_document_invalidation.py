"""Mark current outputs that consume the changed requirement document."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.models.generation_candidates import (
    AiGenerationStageContent,
    RequirementGenerationChain,
)
from testing_agent.repositories.generation_schema import candidate_schema_installed


async def invalidate_document_dependents(session: AsyncSession, requirement_id: str) -> None:
    """Change current-state tokens with the requirement update, without deleting content.

    The caller owns the transaction. UI/API roots are repository/cases and
    interfaces respectively; only material, functional and profile chains
    consume the requirement document directly or through adopted material.
    """
    if not await candidate_schema_installed(session):
        return
    slots = list(
        (
            await session.scalars(
                select(AiGenerationStageContent)
                .join(
                    RequirementGenerationChain,
                    RequirementGenerationChain.chain_id == AiGenerationStageContent.chain_id,
                )
                .where(
                    RequirementGenerationChain.requirement_id == requirement_id,
                    RequirementGenerationChain.kind.in_(
                        ("requirement_analysis", "function", "repository_profile")
                    ),
                    AiGenerationStageContent.source_candidate_id.is_not(None),
                )
                .order_by(AiGenerationStageContent.stage_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    now = datetime.now(UTC)
    for slot in slots:
        slot.invalidated_at = now
        slot.invalidated_reason = "需求原文件已变化，请重新检查来源"
        slot.content_token = uuid4().hex
    await session.flush()
