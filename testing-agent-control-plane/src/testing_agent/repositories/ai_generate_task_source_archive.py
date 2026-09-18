from __future__ import annotations

from sqlalchemy import select

from testing_agent.models.ai_generate_task_source_archive import AiGenerateTaskSourceArchive
from testing_agent.repositories.base import BaseRepository


class AiGenerateTaskSourceArchiveRepository(BaseRepository):
    async def get_source_archive(self, task_id: str) -> AiGenerateTaskSourceArchive | None:
        return await self.session.scalar(
            select(AiGenerateTaskSourceArchive).where(
                AiGenerateTaskSourceArchive.task_id == task_id
            )
        )

    async def get_source_archive_for_update(
        self, task_id: str
    ) -> AiGenerateTaskSourceArchive | None:
        return await self.session.scalar(
            select(AiGenerateTaskSourceArchive)
            .where(AiGenerateTaskSourceArchive.task_id == task_id)
            .with_for_update()
        )

    def add(self, row: AiGenerateTaskSourceArchive) -> None:
        self.session.add(row)

    async def rollback(self) -> None:
        await self.session.rollback()

    async def refresh(self, row: AiGenerateTaskSourceArchive) -> None:
        await self.session.refresh(row)
