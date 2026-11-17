from __future__ import annotations

from sqlalchemy import select

from testing_agent.models.monitoring_connection import MonitoringConnection
from testing_agent.models.project import Project
from testing_agent.repositories.base import ResourceRepository


class MonitoringConnectionRepository(ResourceRepository):
    model = MonitoringConnection
    id_column = "connection_id"

    async def get_project(self, project_id: str) -> Project | None:
        return await self.session.scalar(select(Project).where(Project.project_id == project_id))

    async def get_connection(self, connection_id: str) -> MonitoringConnection | None:
        return await self.session.scalar(
            select(MonitoringConnection).where(MonitoringConnection.connection_id == connection_id)
        )

    async def get_by_project_and_name(
        self, project_id: str, name: str
    ) -> MonitoringConnection | None:
        return await self.session.scalar(
            select(MonitoringConnection).where(
                MonitoringConnection.project_id == project_id,
                MonitoringConnection.name == name,
            )
        )

    async def list_by_project(self, project_id: str) -> list[MonitoringConnection]:
        return list(
            (
                await self.session.scalars(
                    select(MonitoringConnection)
                    .where(MonitoringConnection.project_id == project_id)
                    .order_by(
                        MonitoringConnection.created_at.desc(),
                        MonitoringConnection.id.desc(),
                    )
                )
            ).all()
        )

    def add(self, connection: MonitoringConnection) -> None:
        self.session.add(connection)

    async def refresh(self, connection: MonitoringConnection) -> None:
        await self.session.refresh(connection)
