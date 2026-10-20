"""Database facts for ordinary project access; execution keeps its own locking queries."""

from sqlalchemy import select

from testing_agent.models.project import Project
from testing_agent.models.project_member import ProjectMember
from testing_agent.models.user import User
from testing_agent.repositories.base import BaseRepository


class ProjectAccessRepository(BaseRepository):
    async def is_super_admin(self, user_id: str) -> bool:
        return bool(
            await self.session.scalar(select(User.is_super_admin).where(User.user_id == user_id))
        )

    async def member_role(self, user_id: str, project_id: str) -> str | None:
        return await self.session.scalar(
            select(ProjectMember.role).where(
                ProjectMember.project_id == project_id, ProjectMember.user_id == user_id
            )
        )

    async def project(self, project_id: str) -> Project | None:
        return await self.session.scalar(select(Project).where(Project.project_id == project_id))
