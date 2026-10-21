"""Locking reads for file publication; all commits belong to the workflow."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.models.file_verification import FileVerification
from testing_agent.models.project import Project
from testing_agent.models.project_member import ProjectMember
from testing_agent.models.stored_file import StoredFile
from testing_agent.models.user import User


class FileVerificationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def file(self, file_id: str, *, lock: bool = False) -> StoredFile | None:
        query = select(StoredFile).where(StoredFile.file_id == file_id)
        if lock:
            query = query.with_for_update()
        return await self.session.scalar(query.execution_options(populate_existing=True))

    async def operation(self, operation_id: str) -> FileVerification | None:
        return await self.session.scalar(
            select(FileVerification)
            .where(FileVerification.operation_id == operation_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def access_facts(
        self, project_id: str, user_id: str
    ) -> tuple[Project | None, User | None, str | None]:
        # Match project membership mutations: scope first, then user and membership.
        project = await self.session.scalar(
            select(Project)
            .where(Project.project_id == project_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        user = await self.session.scalar(
            select(User)
            .where(User.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        role = await self.session.scalar(
            select(ProjectMember.role)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
            .with_for_update()
        )
        return project, user, role

    async def garbage(self, bucket: str, now: datetime, limit: int) -> list[FileVerification]:
        return list(
            await self.session.scalars(
                select(FileVerification)
                .where(
                    FileVerification.bucket == bucket,
                    FileVerification.state.in_(["running", "discarded", "abandoned"]),
                    FileVerification.gc_after <= now,
                )
                .order_by(FileVerification.gc_after, FileVerification.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            )
        )
