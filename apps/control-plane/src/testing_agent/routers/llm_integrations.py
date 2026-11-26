from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.integration_connection import list_project_llm_connections
from testing_agent.schemas.common import ApiResponse, ListResponse
from testing_agent.schemas.integrations import IntegrationConnectionResponse

router = APIRouter()

router.get(
    "/projects/{project_id}/integrations/llm/connections",
    response_model=ApiResponse[ListResponse[IntegrationConnectionResponse]],
)(list_project_llm_connections)
