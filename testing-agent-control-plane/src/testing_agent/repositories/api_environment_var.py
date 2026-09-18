from __future__ import annotations

from sqlalchemy import select

from testing_agent.models.api_environment import ApiEnvironment
from testing_agent.models.api_environment_var import ApiEnvironmentVar
from testing_agent.models.project import Project
from testing_agent.repositories.base import BaseRepository


class ApiEnvironmentVarRepository(BaseRepository):
    async def get_project(self, project_id: str) -> Project | None:
        return await self.session.scalar(select(Project).where(Project.project_id == project_id))

    async def get_environment(self, environment_id: str) -> ApiEnvironment | None:
        return await self.session.scalar(
            select(ApiEnvironment).where(
                ApiEnvironment.environment_id == environment_id,
            )
        )

    async def get_var(self, env_var_id: str) -> ApiEnvironmentVar | None:
        return await self.session.scalar(
            select(ApiEnvironmentVar).where(ApiEnvironmentVar.env_var_id == env_var_id)
        )

    async def list_by_environment(self, environment_id: str) -> list[ApiEnvironmentVar]:
        return list(
            (
                await self.session.scalars(
                    select(ApiEnvironmentVar)
                    .where(ApiEnvironmentVar.environment_id == environment_id)
                    .order_by(ApiEnvironmentVar.created_at.asc())
                )
            ).all()
        )

    def add(self, var: ApiEnvironmentVar) -> None:
        self.session.add(var)

    async def delete(self, var: ApiEnvironmentVar) -> None:
        await self.session.delete(var)

    async def refresh(self, var: ApiEnvironmentVar) -> None:
        await self.session.refresh(var)
