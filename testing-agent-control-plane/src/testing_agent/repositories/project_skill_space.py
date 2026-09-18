from __future__ import annotations

from sqlalchemy import select

from testing_agent.models.project import Project
from testing_agent.models.project_skill_space import ProjectSkillSpace
from testing_agent.repositories.base import ResourceRepository


class ProjectSkillSpaceRepository(ResourceRepository):
    model = ProjectSkillSpace
    id_column = "skill_space_id"

    writes_files = True

    async def get_project(self, project_id: str) -> Project | None:
        return await self.session.scalar(select(Project).where(Project.project_id == project_id))

    async def list(self, project_id: str) -> list[ProjectSkillSpace]:
        return list(
            (
                await self.session.scalars(
                    select(ProjectSkillSpace)
                    .where(
                        ProjectSkillSpace.project_id == project_id,
                    )
                    .order_by(ProjectSkillSpace.created_at.desc())
                )
            ).all()
        )

    async def get(self, project_id: str, skill_space_id: str) -> ProjectSkillSpace | None:
        return await self.session.scalar(
            select(ProjectSkillSpace).where(
                ProjectSkillSpace.project_id == project_id,
                ProjectSkillSpace.skill_space_id == skill_space_id,
            )
        )

    async def get_active_by_project_and_filename(
        self, project_id: str, filename: str
    ) -> ProjectSkillSpace | None:
        return await self.session.scalar(
            select(ProjectSkillSpace).where(
                ProjectSkillSpace.project_id == project_id,
                ProjectSkillSpace.filename == filename,
            )
        )

    def add(self, skill: ProjectSkillSpace) -> None:
        self.session.add(skill)

    async def refresh(self, skill: ProjectSkillSpace) -> None:
        await self.session.refresh(skill)
