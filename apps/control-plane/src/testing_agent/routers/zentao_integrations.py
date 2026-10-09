from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from testing_agent.handlers.bug_zentao_import import (
    import_zentao_bugs,
    list_zentao_bug_candidates,
    preview_zentao_bug_import,
)
from testing_agent.handlers.integration_connection import (
    create_project_zentao_connection,
    delete_project_zentao_connection,
    delete_zentao_connection,
    get_project_zentao_connection,
    get_zentao_connection,
    list_project_zentao_connections,
    list_zentao_connections,
    reauth_project_zentao_connection,
    reauth_zentao_connection,
    update_project_zentao_connection,
    update_zentao_connection,
)
from testing_agent.handlers.zentao_mcp import list_zentao_mcp_resources
from testing_agent.schemas.bug_zentao_import import (
    ZentaoBugCandidateItem,
    ZentaoBugImportPreviewResponse,
    ZentaoBugImportResponse,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse
from testing_agent.schemas.integrations import (
    IntegrationConnectionResponse,
)

router = APIRouter()

router.get(
    "/projects/{project_id}/zentao/mcp/{kind}",
    response_model=ApiResponse[ListResponse[Any]],
)(list_zentao_mcp_resources)

router.get(
    "/projects/{project_id}/zentao/bug-imports/candidates",
    response_model=ApiResponse[ListResponse[ZentaoBugCandidateItem]],
)(list_zentao_bug_candidates)
router.post(
    "/projects/{project_id}/zentao/bug-imports/preview",
    response_model=ApiResponse[ZentaoBugImportPreviewResponse],
)(preview_zentao_bug_import)
router.post(
    "/projects/{project_id}/zentao/bug-imports",
    response_model=ApiResponse[ZentaoBugImportResponse],
)(import_zentao_bugs)

router.post(
    "/projects/{project_id}/integrations/zentao/connections",
    response_model=ApiResponse[IntegrationConnectionResponse],
)(create_project_zentao_connection)
router.get(
    "/projects/{project_id}/integrations/zentao/connections",
    response_model=ApiResponse[ListResponse[IntegrationConnectionResponse]],
)(list_project_zentao_connections)
router.get(
    "/projects/{project_id}/integrations/zentao/connections/{connection_id}",
    response_model=ApiResponse[IntegrationConnectionResponse],
)(get_project_zentao_connection)
router.patch(
    "/projects/{project_id}/integrations/zentao/connections/{connection_id}",
    response_model=ApiResponse[IntegrationConnectionResponse],
)(update_project_zentao_connection)
router.post(
    "/projects/{project_id}/integrations/zentao/connections/{connection_id}/reauth",
    response_model=ApiResponse[IntegrationConnectionResponse],
)(reauth_project_zentao_connection)
router.delete(
    "/projects/{project_id}/integrations/zentao/connections/{connection_id}",
    response_model=ApiResponse[EmptyData],
)(delete_project_zentao_connection)

router.get(
    "/integrations/zentao/connections",
    response_model=ApiResponse[ListResponse[IntegrationConnectionResponse]],
)(list_zentao_connections)
router.get(
    "/integrations/zentao/connections/{connection_id}",
    response_model=ApiResponse[IntegrationConnectionResponse],
)(get_zentao_connection)
router.patch(
    "/integrations/zentao/connections/{connection_id}",
    response_model=ApiResponse[IntegrationConnectionResponse],
)(update_zentao_connection)
router.post(
    "/integrations/zentao/connections/{connection_id}/reauth",
    response_model=ApiResponse[IntegrationConnectionResponse],
)(reauth_zentao_connection)
router.delete(
    "/integrations/zentao/connections/{connection_id}",
    response_model=ApiResponse[EmptyData],
)(delete_zentao_connection)
