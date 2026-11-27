from __future__ import annotations

from fastapi import Depends, Query

from testing_agent.api.deps import get_current_user_id, get_integration_connection_service
from testing_agent.core.errors import success_payload
from testing_agent.services.integration_connection import IntegrationConnectionService


async def list_project_gitlab_connections(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(await service.list("gitlab", user_id, project_id))


async def list_project_gitlab_groups(
    project_id: str,
    connection_id: str,
    search: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=100, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(
        await service.list_gitlab_groups(
            user_id=user_id,
            connection_id=connection_id,
            project_id=project_id,
            search=search,
            page=page,
            page_size=page_size,
        )
    )


async def list_project_gitlab_group_repositories(
    project_id: str,
    connection_id: str,
    group_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=100, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(
        await service.list_gitlab_group_repositories(
            user_id=user_id,
            connection_id=connection_id,
            group_id=group_id,
            project_id=project_id,
            page=page,
            page_size=page_size,
        )
    )


async def list_project_gitlab_repository_branches(
    project_id: str,
    connection_id: str,
    repository_id: str,
    search: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=100, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(
        await service.list_gitlab_repository_branches(
            user_id=user_id,
            connection_id=connection_id,
            repository_id=repository_id,
            project_id=project_id,
            search=search,
            page=page,
            page_size=page_size,
        )
    )


async def list_project_zentao_connections(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(await service.list("zentao", user_id, project_id))


async def list_project_llm_connections(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(await service.list("llm", user_id, project_id))
