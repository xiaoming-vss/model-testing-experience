from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.integration_connection import (
    list_project_gitlab_connections,
    list_project_gitlab_group_repositories,
    list_project_gitlab_groups,
    list_project_gitlab_repository_branches,
)
from testing_agent.schemas.common import ApiResponse, ListResponse
from testing_agent.schemas.integrations import (
    GitLabResourceListResponse,
    IntegrationConnectionResponse,
)

router = APIRouter()

router.get(
    "/projects/{project_id}/integrations/gitlab/connections",
    response_model=ApiResponse[ListResponse[IntegrationConnectionResponse]],
)(list_project_gitlab_connections)
router.get(
    "/projects/{project_id}/integrations/gitlab/connections/{connection_id}/groups",
    response_model=ApiResponse[GitLabResourceListResponse],
)(list_project_gitlab_groups)
# group_id/repository_id 支持数字 id 与 URL 编码 path(如 team%2Finfra):
# 编码后的斜杠在路由层被解码,须用 :path 转换器匹配。
router.get(
    "/projects/{project_id}/integrations/gitlab/connections/{connection_id}/groups/{group_id:path}/repositories",
    response_model=ApiResponse[GitLabResourceListResponse],
)(list_project_gitlab_group_repositories)
router.get(
    "/projects/{project_id}/integrations/gitlab/connections/{connection_id}/repositories/{repository_id:path}/branches",
    response_model=ApiResponse[GitLabResourceListResponse],
)(list_project_gitlab_repository_branches)
