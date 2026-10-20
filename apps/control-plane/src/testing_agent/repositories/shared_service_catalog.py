"""Read project catalog rows and current actor-owned authorization associations."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.shared_service import ServiceAuthorization, SharedService


class SharedServiceCatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def resources(self, project_id: str, provider: str) -> list[SharedService]:
        return list(
            await self.session.scalars(
                select(SharedService)
                .where(SharedService.project_id == project_id, SharedService.provider == provider)
                .order_by(SharedService.created_at.desc())
            )
        )

    async def owned_connections(
        self, resources: Sequence[SharedService], user_id: str
    ) -> dict[str, IntegrationConnection]:
        if not resources:
            return {}
        rows = await self.session.execute(
            select(ServiceAuthorization.service_id, IntegrationConnection)
            .join(
                IntegrationConnection,
                ServiceAuthorization.connection_id == IntegrationConnection.connection_id,
            )
            .where(
                ServiceAuthorization.service_id.in_([row.service_id for row in resources]),
                ServiceAuthorization.user_id == user_id,
                IntegrationConnection.user_id == user_id,
            )
            .execution_options(populate_existing=True)
        )
        return {service_id: connection for service_id, connection in rows.all()}
