"""Invalidate previous personal credentials after a confirmed target switch."""

from testing_agent.repositories.integration_connection import IntegrationConnectionRepository
from testing_agent.services.worker_authorization import revoke_executions


async def invalidate_others(session, service_id, current_connection_id=None):
    connections = await IntegrationConnectionRepository(session).list_authorized_by_service(
        service_id, exclude_connection_id=current_connection_id
    )
    notifications = []
    for connection in connections:
        notifications.extend(
            await revoke_executions(
                session, actor=connection.user_id, connection_id=connection.connection_id
            )
        )
        connection.status = "invalid"
        connection.secret_json = {}
    return notifications
