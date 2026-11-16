from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import get_current_user_id, get_software_repository_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.software_repository import (
    SoftwareRepositoryCreateRequest,
    SoftwareRepositoryUpdateRequest,
)
from testing_agent.services.software_repository import SoftwareRepositoryService


async def create_software_repository(
    project_id: str,
    body: SoftwareRepositoryCreateRequest,
    user_id: str = Depends(get_current_user_id),
    service: SoftwareRepositoryService = Depends(get_software_repository_service),
):
    return success_payload(await service.create(user_id, project_id, body))


async def list_software_repositories(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: SoftwareRepositoryService = Depends(get_software_repository_service),
):
    return success_payload(await service.list(user_id, project_id))


async def get_software_repository(
    software_repository_id: str,
    user_id: str = Depends(get_current_user_id),
    service: SoftwareRepositoryService = Depends(get_software_repository_service),
):
    return success_payload(await service.get(user_id, software_repository_id))


async def update_software_repository(
    software_repository_id: str,
    body: SoftwareRepositoryUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    service: SoftwareRepositoryService = Depends(get_software_repository_service),
):
    return success_payload(await service.update(user_id, software_repository_id, body))


async def delete_software_repository(
    software_repository_id: str,
    user_id: str = Depends(get_current_user_id),
    service: SoftwareRepositoryService = Depends(get_software_repository_service),
):
    return success_payload(await service.delete(user_id, software_repository_id))
