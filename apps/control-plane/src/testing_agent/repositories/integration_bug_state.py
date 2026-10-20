"""Current locked records used by integration reservation and local state application."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment
from testing_agent.models.bug_zentao_push import BugZentaoPush


class IntegrationBugStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def push(self, bug_id: str) -> BugZentaoPush | None:
        return await self.session.scalar(
            select(BugZentaoPush)
            .where(BugZentaoPush.bug_id == bug_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def attachment(self, bug_id: str, file_id: str) -> BugZentaoAttachment | None:
        return await self.session.scalar(
            select(BugZentaoAttachment)
            .where(
                BugZentaoAttachment.bug_id == bug_id,
                BugZentaoAttachment.file_id == file_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
