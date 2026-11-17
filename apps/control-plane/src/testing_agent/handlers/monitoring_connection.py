from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import get_current_user_id, get_monitoring_connection_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.monitoring_connection import (
    MonitoringConnectionCreate,
    MonitoringConnectionUpdate,
)
from testing_agent.services.monitoring_connection import MonitoringConnectionService


async def create_monitoring_connection(
    project_id: str,
    body: MonitoringConnectionCreate,
    user_id: str = Depends(get_current_user_id),
    service: MonitoringConnectionService = Depends(get_monitoring_connection_service),
):
    return success_payload(await service.create(user_id, project_id, body))


async def list_monitoring_connections(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: MonitoringConnectionService = Depends(get_monitoring_connection_service),
):
    return success_payload(await service.list(user_id, project_id))


async def get_monitoring_connection(
    connection_id: str,
    user_id: str = Depends(get_current_user_id),
    service: MonitoringConnectionService = Depends(get_monitoring_connection_service),
):
    return success_payload(await service.get(user_id, connection_id))


async def update_monitoring_connection(
    connection_id: str,
    body: MonitoringConnectionUpdate,
    user_id: str = Depends(get_current_user_id),
    service: MonitoringConnectionService = Depends(get_monitoring_connection_service),
):
    return success_payload(await service.update(user_id, connection_id, body))


async def delete_monitoring_connection(
    connection_id: str,
    user_id: str = Depends(get_current_user_id),
    service: MonitoringConnectionService = Depends(get_monitoring_connection_service),
):
    return success_payload(await service.delete(user_id, connection_id))
