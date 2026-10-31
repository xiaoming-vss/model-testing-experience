from __future__ import annotations

from sqlalchemy import select

from testing_agent.models.ai_generate_task_source_archive import AiGenerateTaskSourceArchive
from testing_agent.repositories.base import BaseRepository


class AiGenerateTaskSourceArchiveRepository(BaseRepository):
    async def list_source_archives(
        self, task_ids: list[str]
    ) -> dict[str, AiGenerateTaskSourceArchive]:
        result = {}
        for offset in range(0, len(task_ids), 500):
            rows = await self.session.scalars(
                select(AiGenerateTaskSourceArchive).where(
                    AiGenerateTaskSourceArchive.task_id.in_(task_ids[offset : offset + 500])
                )
            )
            result.update({row.task_id: row for row in rows})
        return result

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
