from __future__ import annotations

from sqlalchemy import select

from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.project import Project
from testing_agent.models.shared_service import ServiceAuthorization
from testing_agent.repositories.base import ResourceRepository


class IntegrationConnectionRepository(ResourceRepository):
    model = IntegrationConnection
    id_column = "connection_id"

    async def get_active_for_user(
        self,
        user_id: str,
        provider: str,
        connection_id: str,
        project_id: str = "",
    ) -> IntegrationConnection | None:
        return await self.session.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.connection_id == connection_id,
                IntegrationConnection.provider == provider,
                IntegrationConnection.status == "active",
                IntegrationConnection.user_id == user_id,
                IntegrationConnection.project_id.in_(("", project_id)),
            )
        )

    async def list_authorized_by_service(
        self, service_id: str, *, exclude_connection_id: str | None = None
    ) -> list[IntegrationConnection]:
        statement = (
            select(IntegrationConnection)
            .join(
                ServiceAuthorization,
                ServiceAuthorization.connection_id == IntegrationConnection.connection_id,
            )
            .where(ServiceAuthorization.service_id == service_id)
        )
        if exclude_connection_id is not None:
            statement = statement.where(
                IntegrationConnection.connection_id != exclude_connection_id
            )
        return list((await self.session.scalars(statement)).all())

    async def get(
        self,
        user_id: str,
        provider: str,
        connection_id: str,
        project_id: str = "",
        *,
        lock: bool = False,
    ) -> IntegrationConnection | None:
        stmt = select(IntegrationConnection).where(
            IntegrationConnection.connection_id == connection_id,
            IntegrationConnection.user_id == user_id,
            IntegrationConnection.provider == provider,
        )
        if project_id:
            stmt = stmt.where(IntegrationConnection.project_id.in_(("", project_id)))
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
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
