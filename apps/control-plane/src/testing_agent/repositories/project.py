from __future__ import annotations

from sqlalchemy import or_, select

from testing_agent.models.project import Project
from testing_agent.models.project_member import ProjectMember
from testing_agent.models.user import User
from testing_agent.repositories.base import ResourceRepository


class ProjectRepository(ResourceRepository):
    model = Project
    id_column = "project_id"

    async def get_active_by_user_and_name(self, user_id: str, name: str) -> Project | None:
        return await self.session.scalar(
            select(Project).where(
                Project.user_id == user_id,
                Project.name == name,
            )
        )

    async def list_active_by_user(self, user_id: str) -> list[Project]:
        return list(
            (
                await self.session.scalars(
                    select(Project)
                    .where(
                        or_(
                            Project.user_id == user_id,
                            Project.project_id.in_(
                                select(ProjectMember.project_id).where(
                                    ProjectMember.user_id == user_id
                                )
                            ),
                        ),
                    )
                    .order_by(Project.created_at.desc())
                )
            ).all()
        )

    async def list_all_active(self) -> list[Project]:
        return list(
            (await self.session.scalars(select(Project).order_by(Project.created_at.desc()))).all()
        )

    async def owner(self, user_id: str) -> User | None:
        return await self.session.scalar(select(User).where(User.user_id == user_id))

    async def member_rows(self, project_id: str) -> list[tuple[User, str]]:
        rows = await self.session.execute(
            select(User, ProjectMember.role)
            .join(ProjectMember, ProjectMember.user_id == User.user_id)
            .where(ProjectMember.project_id == project_id)
            .order_by(User.nickname)
        )
        return [(user, role) for user, role in rows]

    def add(self, project: Project) -> None:
        self.session.add(project)

    async def refresh(self, project: Project) -> None:
        await self.session.refresh(project)
