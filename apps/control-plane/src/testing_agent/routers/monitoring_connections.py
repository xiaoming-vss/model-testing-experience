from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.monitoring_connection import (
    create_monitoring_connection,
    delete_monitoring_connection,
    get_monitoring_connection,
    list_monitoring_connections,
    update_monitoring_connection,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse
from testing_agent.schemas.monitoring_connection import MonitoringConnectionResponse

router = APIRouter()

router.post(
    "/projects/{project_id}/monitoring-connections",
    response_model=ApiResponse[MonitoringConnectionResponse],
)(create_monitoring_connection)
router.get(
    "/projects/{project_id}/monitoring-connections",
    response_model=ApiResponse[ListResponse[MonitoringConnectionResponse]],
)(list_monitoring_connections)
router.get(
    "/monitoring-connections/{connection_id}",
    response_model=ApiResponse[MonitoringConnectionResponse],
)(get_monitoring_connection)
router.patch(
    "/monitoring-connections/{connection_id}",
    response_model=ApiResponse[MonitoringConnectionResponse],
)(update_monitoring_connection)
router.delete(
    "/monitoring-connections/{connection_id}",
    response_model=ApiResponse[EmptyData],
)(delete_monitoring_connection)
