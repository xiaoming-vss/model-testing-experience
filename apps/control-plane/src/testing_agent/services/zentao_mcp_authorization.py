"""Invalidate previous personal credentials after a confirmed target switch."""

from sqlalchemy import select

from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.shared_service import ServiceAuthorization
from testing_agent.services.worker_authorization import revoke_executions


async def invalidate_others(session, service_id, current_connection_id=None):
    statement = (
        select(IntegrationConnection)
        .join(
            ServiceAuthorization,
            ServiceAuthorization.connection_id == IntegrationConnection.connection_id,
        )
        .where(ServiceAuthorization.service_id == service_id)
    )
    if current_connection_id is not None:
        statement = statement.where(IntegrationConnection.connection_id != current_connection_id)
    connections = await session.scalars(statement)
    for connection in connections:
        await revoke_executions(
            session, actor=connection.user_id, connection_id=connection.connection_id
        )
        connection.status = "invalid"
        connection.secret_json = {}
