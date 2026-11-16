from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.requirement_software_repository import (
    create_requirement_software_repository,
    delete_requirement_software_repository,
    list_requirement_software_repositories,
    update_requirement_software_repository,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse
from testing_agent.schemas.requirement_software_repository import (
    RequirementSoftwareRepositoryResponse,
)

router = APIRouter()

router.get(
    "/requirements/{requirement_id}/software-repositories",
    response_model=ApiResponse[ListResponse[RequirementSoftwareRepositoryResponse]],
)(list_requirement_software_repositories)
router.post(
    "/requirements/{requirement_id}/software-repositories",
    response_model=ApiResponse[RequirementSoftwareRepositoryResponse],
)(create_requirement_software_repository)
router.patch(
    "/requirements/{requirement_id}/software-repositories/{software_repository_id}",
    response_model=ApiResponse[RequirementSoftwareRepositoryResponse],
)(update_requirement_software_repository)
router.delete(
    "/requirements/{requirement_id}/software-repositories/{software_repository_id}",
    response_model=ApiResponse[EmptyData],
)(delete_requirement_software_repository)
