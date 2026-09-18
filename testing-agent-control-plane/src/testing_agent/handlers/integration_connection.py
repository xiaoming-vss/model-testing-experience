from __future__ import annotations

from fastapi import Depends, Query

from testing_agent.api.deps import get_current_user_id, get_integration_connection_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.integrations import (
    CreateGitLabIntegrationConnectionRequest,
    CreateLLMIntegrationConnectionRequest,
    CreateZentaoIntegrationConnectionRequest,
    UpdateGitLabIntegrationConnectionRequest,
    UpdateLLMIntegrationConnectionRequest,
    UpdateZentaoIntegrationConnectionRequest,
)
from testing_agent.services.integration_connection import IntegrationConnectionService


async def create_project_gitlab_connection(
    project_id: str,
    body: CreateGitLabIntegrationConnectionRequest,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(
        await service.create("gitlab", body.model_dump(by_alias=True), user_id, project_id)
    )


async def list_project_gitlab_connections(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(await service.list("gitlab", user_id, project_id))


async def get_project_gitlab_connection(
    project_id: str,
    connection_id: str,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(await service.get("gitlab", connection_id, user_id, project_id))


async def update_project_gitlab_connection(
    project_id: str,
    connection_id: str,
    body: UpdateGitLabIntegrationConnectionRequest,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(
        await service.update(
            "gitlab",
            connection_id,
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
            project_id,
        )
    )


async def reauth_project_gitlab_connection(
    project_id: str,
    connection_id: str,
    body: UpdateGitLabIntegrationConnectionRequest | None = None,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    payload = body.model_dump(by_alias=True, exclude_none=True) if body else None
    return success_payload(await service.reauth_gitlab(connection_id, payload, user_id, project_id))


async def delete_project_gitlab_connection(
    project_id: str,
    connection_id: str,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(await service.delete("gitlab", connection_id, user_id, project_id))


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


async def create_project_zentao_connection(
    project_id: str,
    body: CreateZentaoIntegrationConnectionRequest,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(
        await service.create("zentao", body.model_dump(by_alias=True), user_id, project_id)
    )


async def list_zentao_connections(
    project_id: str = Query(default="", alias="projectId"),
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(await service.list("zentao", user_id, project_id))


async def list_project_zentao_connections(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(await service.list("zentao", user_id, project_id))


async def get_zentao_connection(
    connection_id: str,
    project_id: str = Query(default="", alias="projectId"),
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(await service.get("zentao", connection_id, user_id, project_id))


async def get_project_zentao_connection(
    project_id: str,
    connection_id: str,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(await service.get("zentao", connection_id, user_id, project_id))


async def update_zentao_connection(
    connection_id: str,
    body: UpdateZentaoIntegrationConnectionRequest,
    project_id: str = Query(default="", alias="projectId"),
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(
        await service.update(
            "zentao",
            connection_id,
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
            project_id,
        )
    )


async def update_project_zentao_connection(
    project_id: str,
    connection_id: str,
    body: UpdateZentaoIntegrationConnectionRequest,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(
        await service.update(
            "zentao",
            connection_id,
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
            project_id,
        )
    )


async def reauth_zentao_connection(
    connection_id: str,
    body: UpdateZentaoIntegrationConnectionRequest | None = None,
    project_id: str = Query(default="", alias="projectId"),
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    payload = body.model_dump(by_alias=True, exclude_none=True) if body else None
    return success_payload(await service.reauth_zentao(connection_id, payload, user_id, project_id))


async def reauth_project_zentao_connection(
    project_id: str,
    connection_id: str,
    body: UpdateZentaoIntegrationConnectionRequest | None = None,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    payload = body.model_dump(by_alias=True, exclude_none=True) if body else None
    return success_payload(await service.reauth_zentao(connection_id, payload, user_id, project_id))


async def delete_zentao_connection(
    connection_id: str,
    project_id: str = Query(default="", alias="projectId"),
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(await service.delete("zentao", connection_id, user_id, project_id))


async def delete_project_zentao_connection(
    project_id: str,
    connection_id: str,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(await service.delete("zentao", connection_id, user_id, project_id))


async def list_zentao_projects(
    connection_id: str,
    project_id: str = Query(default="", alias="projectId"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(
        await service.list_zentao_projects(
            connection_id,
            user_id,
            project_id=project_id,
            page=page,
            page_size=page_size,
        )
    )


async def list_project_zentao_projects(
    project_id: str,
    connection_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(
        await service.list_zentao_projects(
            connection_id,
            user_id,
            project_id=project_id,
            page=page,
            page_size=page_size,
        )
    )


async def list_zentao_project_executions(
    connection_id: str,
    remote_project_id: str,
    project_id: str = Query(default="", alias="projectId"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(
        await service.list_zentao_project_executions(
            connection_id,
            remote_project_id,
            user_id,
            project_id=project_id,
            page=page,
            page_size=page_size,
        )
    )


async def list_project_zentao_project_executions(
    project_id: str,
    connection_id: str,
    remote_project_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(
        await service.list_zentao_project_executions(
            connection_id,
            remote_project_id,
            user_id,
            project_id=project_id,
            page=page,
            page_size=page_size,
        )
    )


async def list_zentao_execution_testtasks(
    connection_id: str,
    remote_execution_id: str,
    project_id: str = Query(default="", alias="projectId"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(
        await service.list_zentao_execution_testtasks(
            connection_id,
            remote_execution_id,
            user_id,
            project_id=project_id,
            page=page,
            page_size=page_size,
        )
    )


async def list_project_zentao_execution_testtasks(
    project_id: str,
    connection_id: str,
    remote_execution_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(
        await service.list_zentao_execution_testtasks(
            connection_id,
            remote_execution_id,
            user_id,
            project_id=project_id,
            page=page,
            page_size=page_size,
        )
    )


async def list_zentao_execution_stories(
    connection_id: str,
    remote_execution_id: str,
    project_id: str = Query(default="", alias="projectId"),
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(
        await service.list_zentao_execution_stories(
            connection_id,
            remote_execution_id,
            user_id,
            project_id,
        )
    )


async def list_project_zentao_execution_stories(
    project_id: str,
    connection_id: str,
    remote_execution_id: str,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(
        await service.list_zentao_execution_stories(
            connection_id,
            remote_execution_id,
            user_id,
            project_id,
        )
    )


async def list_zentao_execution_cases(
    connection_id: str,
    remote_execution_id: str,
    project_id: str = Query(default="", alias="projectId"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(
        await service.list_zentao_execution_cases(
            connection_id,
            remote_execution_id,
            user_id,
            project_id=project_id,
            page=page,
            page_size=page_size,
        )
    )


async def list_project_zentao_execution_cases(
    project_id: str,
    connection_id: str,
    remote_execution_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000, alias="pageSize"),
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(
        await service.list_zentao_execution_cases(
            connection_id,
            remote_execution_id,
            user_id,
            project_id=project_id,
            page=page,
            page_size=page_size,
        )
    )


async def create_llm_connection(
    body: CreateLLMIntegrationConnectionRequest,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(await service.create("llm", body.model_dump(by_alias=True), user_id))


async def create_project_llm_connection(
    project_id: str,
    body: CreateLLMIntegrationConnectionRequest,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(
        await service.create("llm", body.model_dump(by_alias=True), user_id, project_id)
    )


async def list_llm_connections(
    project_id: str = Query(default="", alias="projectId"),
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(await service.list("llm", user_id, project_id))


async def list_project_llm_connections(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(await service.list("llm", user_id, project_id))


async def get_llm_connection(
    connection_id: str,
    project_id: str = Query(default="", alias="projectId"),
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(await service.get("llm", connection_id, user_id, project_id))


async def get_project_llm_connection(
    project_id: str,
    connection_id: str,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(await service.get("llm", connection_id, user_id, project_id))


async def update_llm_connection(
    connection_id: str,
    body: UpdateLLMIntegrationConnectionRequest,
    project_id: str = Query(default="", alias="projectId"),
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(
        await service.update(
            "llm",
            connection_id,
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
            project_id,
        )
    )


async def update_project_llm_connection(
    project_id: str,
    connection_id: str,
    body: UpdateLLMIntegrationConnectionRequest,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(
        await service.update(
            "llm",
            connection_id,
            body.model_dump(by_alias=True, exclude_none=True),
            user_id,
            project_id,
        )
    )


async def delete_llm_connection(
    connection_id: str,
    project_id: str = Query(default="", alias="projectId"),
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(await service.delete("llm", connection_id, user_id, project_id))


async def delete_project_llm_connection(
    project_id: str,
    connection_id: str,
    user_id: str = Depends(get_current_user_id),
    service: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return success_payload(await service.delete("llm", connection_id, user_id, project_id))
