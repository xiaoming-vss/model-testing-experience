from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import (
    get_current_user_id,
    get_requirement_software_repository_service,
)
from testing_agent.core.errors import success_payload
from testing_agent.schemas.requirement_software_repository import (
    RequirementSoftwareRepositoryCreateRequest,
    RequirementSoftwareRepositoryUpdateRequest,
)
from testing_agent.services.requirement_software_repository import (
    RequirementSoftwareRepositoryService,
)


async def list_requirement_software_repositories(
    requirement_id: str,
    user_id: str = Depends(get_current_user_id),
    service: RequirementSoftwareRepositoryService = Depends(
        get_requirement_software_repository_service
    ),
):
    return success_payload(await service.list(user_id, requirement_id))


async def create_requirement_software_repository(
    requirement_id: str,
    body: RequirementSoftwareRepositoryCreateRequest,
    user_id: str = Depends(get_current_user_id),
    service: RequirementSoftwareRepositoryService = Depends(
        get_requirement_software_repository_service
    ),
):
    return success_payload(await service.create(user_id, requirement_id, body))


async def update_requirement_software_repository(
    requirement_id: str,
    software_repository_id: str,
    body: RequirementSoftwareRepositoryUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    service: RequirementSoftwareRepositoryService = Depends(
        get_requirement_software_repository_service
    ),
):
    return success_payload(
        await service.update(user_id, requirement_id, software_repository_id, body)
    )


async def delete_requirement_software_repository(
    requirement_id: str,
    software_repository_id: str,
    user_id: str = Depends(get_current_user_id),
    service: RequirementSoftwareRepositoryService = Depends(
        get_requirement_software_repository_service
    ),
):
    return success_payload(await service.delete(user_id, requirement_id, software_repository_id))
