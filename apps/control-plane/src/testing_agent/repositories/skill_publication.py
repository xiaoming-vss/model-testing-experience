"""Current catalog and file facts for atomic skill publication."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.models.file_verification import FileVerification
from testing_agent.models.project import Project
from testing_agent.models.project_skill_space import ProjectSkillSpace
from testing_agent.models.stored_file import StoredFile


class SkillPublicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def catalog(self, name: str) -> list[ProjectSkillSpace]:
        return list(
            await self.session.scalars(
                select(ProjectSkillSpace)
                .where(ProjectSkillSpace.filename == name)
                .order_by(ProjectSkillSpace.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )

    async def scope(self, project_id: str) -> Project | None:
        return await self.session.scalar(
            select(Project)
            .where(Project.project_id == project_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def files(self, identifiers: list[str]) -> dict[str, StoredFile]:
        rows = await self.session.scalars(
            select(StoredFile)
            .where(StoredFile.file_id.in_(identifiers))
            .order_by(StoredFile.file_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return {row.file_id: row for row in rows}

    async def operations(self, identifiers: list[str]) -> dict[str, FileVerification]:
        rows = await self.session.scalars(
            select(FileVerification)
            .where(FileVerification.operation_id.in_(identifiers))
            .order_by(FileVerification.operation_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return {row.operation_id: row for row in rows}

    async def skill(self, identifier: str) -> ProjectSkillSpace | None:
        return await self.session.scalar(
            select(ProjectSkillSpace)
            .where(ProjectSkillSpace.skill_space_id == identifier)
            .execution_options(populate_existing=True)
        )

    async def identifiers(self) -> list[str]:
        return list(
            await self.session.scalars(
                select(ProjectSkillSpace.skill_space_id).order_by(ProjectSkillSpace.id)
            )
        )
