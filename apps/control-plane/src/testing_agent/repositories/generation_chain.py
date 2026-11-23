"""Read models for requirement generation chains."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.models.generation_candidates import RequirementGenerationChain
from testing_agent.repositories.generation_schema import candidate_schema_installed


class GenerationChainRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def candidate_chain_task(self, requirement_id: str, kind: str) -> str | None:
        """Return the explicitly bound current task, if this chain has switched."""
        if not await candidate_schema_installed(self.session):
            return None
        return await self.session.scalar(
            select(RequirementGenerationChain.task_id).where(
                RequirementGenerationChain.requirement_id == requirement_id,
                RequirementGenerationChain.kind == kind,
            )
        )
