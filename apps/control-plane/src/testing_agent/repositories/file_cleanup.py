"""Bounded cleanup claims and historical-reference facts."""

from datetime import datetime

from sqlalchemy import exists, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.models.bug import Bug
from testing_agent.models.file_verification import FileVerification
from testing_agent.models.stored_file import StoredFile


class FileCleanupRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def candidates(
        self, bucket: str, now: datetime, *, staging: bool, limit: int
    ) -> list[StoredFile]:
        conditions = [
            StoredFile.bucket == bucket,
            StoredFile.expires_at < now,
            or_(StoredFile.cleanup_until.is_(None), StoredFile.cleanup_until <= now),
        ]
        if staging:
            conditions += [
                StoredFile.status.in_(["attached", "archived"]),
                StoredFile.staging_key != "",
            ]
        else:
            conditions += [
                StoredFile.status.in_(["pending", "ready", "deleting"]),
                ~exists().where(
                    FileVerification.operation_id == StoredFile.verification_id,
                    FileVerification.state == "running",
                ),
            ]
        return list(
            await self.session.scalars(
                select(StoredFile)
                .where(*conditions)
                .order_by(StoredFile.expires_at, StoredFile.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            )
        )

    async def existing_bugs(self, rows: list[StoredFile]) -> set[tuple[str, str]]:
        keys = [
            (row.project_id, row.resource_id)
            for row in rows
            if row.resource_type == "bug"
            and row.status == "deleting"
            and row.completed_at is not None
        ]
        if not keys:
            return set()
        result = await self.session.execute(
            select(Bug.project_id, Bug.bug_id).where(tuple_(Bug.project_id, Bug.bug_id).in_(keys))
        )
        return {(project, bug) for project, bug in result}

    async def live_keys(self, bucket: str, keys: list[str]) -> set[str]:
        if not keys:
            return set()
        return set(
            await self.session.scalars(
                select(StoredFile.object_key).where(
                    StoredFile.bucket == bucket,
                    StoredFile.object_key.in_(keys),
                    StoredFile.status.in_(["pending", "ready", "attached", "archived"]),
                )
            )
        )

    async def current(self, file_id: str) -> StoredFile | None:
        return await self.session.scalar(
            select(StoredFile)
            .where(StoredFile.file_id == file_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
