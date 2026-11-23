"""Detect whether the candidate tables have been installed on this database.

Pre-release deployments may still use the original baseline.  Probing the
schema keeps their existing workflows readable until an explicit upgrade.
"""

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationReviewReceipt,
    AiGenerationStageContent,
    RequirementGenerationChain,
)

_CANDIDATE_TABLES = frozenset(
    model.__tablename__
    for model in (
        RequirementGenerationChain,
        AiGenerationCandidate,
        AiGenerationStageContent,
        AiGenerationReviewReceipt,
    )
)


async def candidate_schema_installed(session: AsyncSession) -> bool:
    def installed_tables(sync_session: Session) -> set[str]:
        # A request-scoped session can build several chain views. An upgrade
        # happens offline, never halfway through an active request.
        key = "generation_candidate_tables"
        cached = sync_session.info.get(key)
        if cached is None:
            cached = set(inspect(sync_session.connection()).get_table_names()) & _CANDIDATE_TABLES
            sync_session.info[key] = cached
        return cached

    installed = await session.run_sync(installed_tables)
    if installed and installed != _CANDIDATE_TABLES:
        raise dynamic_error(ErrBadRequest, "候选数据表不完整，请先完成数据库升级")
    return bool(installed)
