from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import get_current_user_id, get_project_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.project import CreateProjectRequest, UpdateProjectRequest
from testing_agent.schemas.project_member import (
    AddProjectMemberRequest,
    ChangeProjectMemberRequest,
    TransferProjectRequest,
)
from testing_agent.services.project import ProjectService


async def create_project(
    body: CreateProjectRequest,
    user_id: str = Depends(get_current_user_id),
    service: ProjectService = Depends(get_project_service),
):
    return success_payload(await service.create(user_id, body))


async def list_projects(
    user_id: str = Depends(get_current_user_id),
    service: ProjectService = Depends(get_project_service),
):
    return success_payload(await service.list(user_id))


async def get_project(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ProjectService = Depends(get_project_service),
):
    return success_payload(await service.get(user_id, project_id))


async def update_project(
    project_id: str,
    body: UpdateProjectRequest,
    user_id: str = Depends(get_current_user_id),
    service: ProjectService = Depends(get_project_service),
):
    return success_payload(await service.update(user_id, project_id, body))


async def delete_project(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ProjectService = Depends(get_project_service),
):
    return success_payload(await service.delete(user_id, project_id))


async def add_project_member(
    project_id: str,
    body: AddProjectMemberRequest,
    user_id: str = Depends(get_current_user_id),
    service: ProjectService = Depends(get_project_service),
):
    return success_payload(await service.add_member(user_id, project_id, body))


async def list_project_members(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ProjectService = Depends(get_project_service),
):
    return success_payload(await service.list_members(user_id, project_id))


async def change_project_member(
    project_id: str,
    member_id: str,
    body: ChangeProjectMemberRequest,
    user_id: str = Depends(get_current_user_id),
    service: ProjectService = Depends(get_project_service),
):
    return success_payload(await service.change_member(user_id, project_id, member_id, body.role))


async def remove_project_member(
    project_id: str,
    member_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ProjectService = Depends(get_project_service),
):
    return success_payload(await service.remove_member(user_id, project_id, member_id))


async def leave_project(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ProjectService = Depends(get_project_service),
):
    return success_payload(await service.remove_member(user_id, project_id, user_id))


async def transfer_project(
    project_id: str,
    body: TransferProjectRequest,
    user_id: str = Depends(get_current_user_id),
    service: ProjectService = Depends(get_project_service),
):
    return success_payload(await service.transfer(user_id, project_id, body.user_id))
