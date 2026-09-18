"""Credential access is always bound to an actor, separately from project roles."""

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.enums import ConnectionStatus
from testing_agent.core.errors import ErrIntegrationConnectionAuthFailed, ErrNotFound
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.repositories.integration_connection import IntegrationConnectionRepository


async def require_personal_connection(
    session: AsyncSession, user_id: str, provider: str, connection_id: str, project_id: str
) -> IntegrationConnection:
    connection = await IntegrationConnectionRepository(session).get(
        user_id, provider, connection_id, project_id
    )
    if connection is None:
        raise ErrNotFound
    if connection.status != ConnectionStatus.ACTIVE.value:
        raise ErrIntegrationConnectionAuthFailed
    if provider == "llm" and not (connection.secret_json or {}).get("apiKey"):
        raise ErrIntegrationConnectionAuthFailed
    return connection
