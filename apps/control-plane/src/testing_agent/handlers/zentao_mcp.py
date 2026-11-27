"""Binding candidate queries use the project's MCP and the caller's own token."""

from typing import Literal

from fastapi import Depends, Query

from testing_agent.api.deps import get_current_user_id, get_zentao_mcp_candidate_query
from testing_agent.core.errors import success_payload
from testing_agent.services.zentao_mcp import ZentaoMcpCandidateQuery


async def list_zentao_mcp_resources(
    project_id: str,
    kind: Literal["projects", "executions", "stories"],
    parent_id: int | None = Query(default=None, alias="parentId", gt=0),
    mcp_service_id: str = Query(default="", alias="mcpServiceId"),
    user_id: str = Depends(get_current_user_id),
    query: ZentaoMcpCandidateQuery = Depends(get_zentao_mcp_candidate_query),
):
    return success_payload(
        await query.list(
            user_id=user_id,
            project_id=project_id,
            kind=kind,
            parent_id=str(parent_id or ""),
            mcp_service_id=mcp_service_id,
        )
    )
