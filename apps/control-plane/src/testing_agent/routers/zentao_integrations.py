from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from testing_agent.handlers.bug_zentao_import import (
    import_zentao_bugs,
    list_zentao_bug_candidates,
    preview_zentao_bug_import,
)
from testing_agent.handlers.integration_connection import list_project_zentao_connections
from testing_agent.handlers.zentao_mcp import list_zentao_mcp_resources
from testing_agent.schemas.bug_zentao_import import (
    ZentaoBugCandidateListResponse,
    ZentaoBugImportPreviewResponse,
    ZentaoBugImportResponse,
)
from testing_agent.schemas.common import ApiResponse, ListResponse
from testing_agent.schemas.integrations import IntegrationConnectionResponse

router = APIRouter()

router.get(
    "/projects/{project_id}/zentao/mcp/{kind}",
    response_model=ApiResponse[ListResponse[Any]],
)(list_zentao_mcp_resources)

router.get(
    "/projects/{project_id}/zentao/bug-imports/candidates",
    response_model=ApiResponse[ZentaoBugCandidateListResponse],
)(list_zentao_bug_candidates)
router.post(
    "/projects/{project_id}/zentao/bug-imports/preview",
    response_model=ApiResponse[ZentaoBugImportPreviewResponse],
)(preview_zentao_bug_import)
router.post(
    "/projects/{project_id}/zentao/bug-imports",
    response_model=ApiResponse[ZentaoBugImportResponse],
)(import_zentao_bugs)

router.get(
    "/projects/{project_id}/integrations/zentao/connections",
    response_model=ApiResponse[ListResponse[IntegrationConnectionResponse]],
)(list_project_zentao_connections)
