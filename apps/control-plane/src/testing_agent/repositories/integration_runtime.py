from __future__ import annotations

from sqlalchemy import select

from testing_agent.models.integration_job import IntegrationRestoreReview, IntegrationRuntime
from testing_agent.repositories.base import BaseRepository


class IntegrationRuntimeRepository(BaseRepository):
    async def restored(self) -> IntegrationRuntime | None:
        return await self.session.scalar(
            select(IntegrationRuntime).where(IntegrationRuntime.id == 1)
        )

    async def isolated_scope(self, bug_id: str) -> bool:
        return (
            await self.session.scalar(
                select(IntegrationRestoreReview.review_id)
                .join(
                    IntegrationRuntime,
                    IntegrationRuntime.restore_id == IntegrationRestoreReview.restore_id,
                )
                .where(
                    IntegrationRuntime.id == 1,
                    IntegrationRestoreReview.scope_type == "bug",
                    IntegrationRestoreReview.scope_id == bug_id,
                    IntegrationRestoreReview.decision == "isolated",
                )
                .limit(1)
            )
            is not None
        )
