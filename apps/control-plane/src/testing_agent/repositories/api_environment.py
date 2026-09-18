from __future__ import annotations

from sqlalchemy import select

from testing_agent.models.api_environment import ApiEnvironment
from testing_agent.models.project import Project
from testing_agent.repositories.base import ResourceRepository


class ApiEnvironmentRepository(ResourceRepository):
    model = ApiEnvironment
    id_column = "environment_id"

    async def get_project(self, project_id: str) -> Project | None:
        return await self.session.scalar(select(Project).where(Project.project_id == project_id))

    async def get_environment(self, environment_id: str) -> ApiEnvironment | None:
        return await self.session.scalar(
            select(ApiEnvironment).where(
                ApiEnvironment.environment_id == environment_id,
            )
        )

    async def list_by_project(self, project_id: str) -> list[ApiEnvironment]:
        return list(
            (
                await self.session.scalars(
                    select(ApiEnvironment)
                    .where(
                        ApiEnvironment.project_id == project_id,
                    )
                    .order_by(ApiEnvironment.created_at.desc())
                )
            ).all()
        )

    def add(self, environment: ApiEnvironment) -> None:
        self.session.add(environment)

    async def refresh(self, environment: ApiEnvironment) -> None:
        await self.session.refresh(environment)
