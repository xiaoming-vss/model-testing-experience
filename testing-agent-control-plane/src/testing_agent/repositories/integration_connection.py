from __future__ import annotations

from sqlalchemy import select

from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.project import Project
from testing_agent.repositories.base import ResourceRepository


class IntegrationConnectionRepository(ResourceRepository):
    model = IntegrationConnection
    id_column = "connection_id"

    async def get(
        self, user_id: str, provider: str, connection_id: str, project_id: str = ""
    ) -> IntegrationConnection | None:
        stmt = select(IntegrationConnection).where(
            IntegrationConnection.connection_id == connection_id,
            IntegrationConnection.user_id == user_id,
            IntegrationConnection.provider == provider,
        )
        if project_id:
            stmt = stmt.where(IntegrationConnection.project_id.in_(("", project_id)))
        return await self.session.scalar(stmt)

    async def list(
        self, user_id: str, provider: str, project_id: str = ""
    ) -> list[IntegrationConnection]:
        stmt = select(IntegrationConnection).where(
            IntegrationConnection.user_id == user_id,
            IntegrationConnection.provider == provider,
        )
        if project_id:
            stmt = stmt.where(IntegrationConnection.project_id.in_(("", project_id)))
        return list(
            (
                await self.session.scalars(stmt.order_by(IntegrationConnection.created_at.desc()))
            ).all()
        )

    async def get_project(self, project_id: str) -> Project | None:
        return await self.session.scalar(select(Project).where(Project.project_id == project_id))

    def add(self, connection: IntegrationConnection) -> None:
        self.session.add(connection)

    async def refresh(self, connection: IntegrationConnection) -> None:
        await self.session.refresh(connection)
