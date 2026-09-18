from __future__ import annotations

from fastapi import Depends

from testing_agent.api.deps import get_current_user_id, get_sprint_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.sprint import CreateSprintRequest, UpdateSprintRequest
from testing_agent.services.sprint import SprintService


async def create_sprint(
    project_id: str,
    body: CreateSprintRequest,
    user_id: str = Depends(get_current_user_id),
    service: SprintService = Depends(get_sprint_service),
):
    return success_payload(await service.create(user_id, project_id, body))


async def list_sprints(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: SprintService = Depends(get_sprint_service),
):
    return success_payload(await service.list(user_id, project_id))


async def get_sprint(
    sprint_id: str,
    user_id: str = Depends(get_current_user_id),
    service: SprintService = Depends(get_sprint_service),
):
    return success_payload(await service.get(user_id, sprint_id))


async def update_sprint(
    sprint_id: str,
    body: UpdateSprintRequest,
    user_id: str = Depends(get_current_user_id),
    service: SprintService = Depends(get_sprint_service),
):
    return success_payload(await service.update(user_id, sprint_id, body))


async def delete_sprint(
    sprint_id: str,
    user_id: str = Depends(get_current_user_id),
    service: SprintService = Depends(get_sprint_service),
):
    return success_payload(await service.delete(user_id, sprint_id))
