from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.integration_connection import (
    create_llm_connection,
    create_project_llm_connection,
    delete_llm_connection,
    delete_project_llm_connection,
    get_llm_connection,
    get_project_llm_connection,
    list_llm_connections,
    list_project_llm_connections,
    update_llm_connection,
    update_project_llm_connection,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse
from testing_agent.schemas.integrations import IntegrationConnectionResponse

router = APIRouter()

router.post(
    "/projects/{project_id}/integrations/llm/connections",
    response_model=ApiResponse[IntegrationConnectionResponse],
)(create_project_llm_connection)
router.get(
    "/projects/{project_id}/integrations/llm/connections",
    response_model=ApiResponse[ListResponse[IntegrationConnectionResponse]],
)(list_project_llm_connections)
router.get(
    "/projects/{project_id}/integrations/llm/connections/{connection_id}",
    response_model=ApiResponse[IntegrationConnectionResponse],
)(get_project_llm_connection)
router.patch(
    "/projects/{project_id}/integrations/llm/connections/{connection_id}",
    response_model=ApiResponse[IntegrationConnectionResponse],
)(update_project_llm_connection)
router.delete(
    "/projects/{project_id}/integrations/llm/connections/{connection_id}",
    response_model=ApiResponse[EmptyData],
)(delete_project_llm_connection)

router.post(
    "/integrations/llm/connections",
    response_model=ApiResponse[IntegrationConnectionResponse],
)(create_llm_connection)
router.get(
    "/integrations/llm/connections",
    response_model=ApiResponse[ListResponse[IntegrationConnectionResponse]],
)(list_llm_connections)
router.get(
    "/integrations/llm/connections/{connection_id}",
    response_model=ApiResponse[IntegrationConnectionResponse],
)(get_llm_connection)
router.patch(
    "/integrations/llm/connections/{connection_id}",
    response_model=ApiResponse[IntegrationConnectionResponse],
)(update_llm_connection)
router.delete(
    "/integrations/llm/connections/{connection_id}",
    response_model=ApiResponse[EmptyData],
)(delete_llm_connection)
