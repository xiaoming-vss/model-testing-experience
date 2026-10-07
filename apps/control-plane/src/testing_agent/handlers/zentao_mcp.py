"""Binding candidate queries use the project's MCP and the caller's own token."""

from typing import Literal

from fastapi import Depends, Query

from testing_agent.api.deps import get_current_user_id, get_integration_connection_service
from testing_agent.core.errors import ErrBadRequest, success_payload
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.zentao_mcp import ZentaoMcpAccess, ZentaoMcpResources


async def list_zentao_mcp_resources(
    project_id: str,
    kind: Literal["projects", "executions", "stories"],
    parent_id: int | None = Query(default=None, alias="parentId", gt=0),
    mcp_service_id: str = Query(default="", alias="mcpServiceId"),
    user_id: str = Depends(get_current_user_id),
    connections: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    if kind != "projects" and parent_id is None:
        raise ErrBadRequest()
    access = await ZentaoMcpAccess(connections).resolve(
        user_id, project_id, mcp_service_id=mcp_service_id
    )
    result = await ZentaoMcpResources().read(access, kind, str(parent_id or ""))
    items = [item for item in result["items"] if not item["deleted"]]
    return success_payload({"items": items, "total": len(items)})
