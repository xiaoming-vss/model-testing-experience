from __future__ import annotations

from fastapi import Depends, Header, Query
from fastapi.responses import JSONResponse, RedirectResponse

from testing_agent.api.deps import get_current_user_id, get_requirement_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.requirement import CreateRequirementRequest, UpdateRequirementRequest
from testing_agent.services.requirement import RequirementService


async def create_requirement(
    sprint_id: str,
    body: CreateRequirementRequest,
    user_id: str = Depends(get_current_user_id),
    service: RequirementService = Depends(get_requirement_service),
):
    return success_payload(await service.create(user_id, sprint_id, body))


async def list_requirements(
    sprint_id: str,
    user_id: str = Depends(get_current_user_id),
    service: RequirementService = Depends(get_requirement_service),
):
    return success_payload(await service.list(user_id, sprint_id))


async def get_requirement(
    requirement_id: str,
    user_id: str = Depends(get_current_user_id),
    service: RequirementService = Depends(get_requirement_service),
):
    return success_payload(await service.get(user_id, requirement_id))


async def list_project_requirements(
    project_id: str,
    sprint_id: str | None = Query(default=None, alias="sprintId", min_length=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    service: RequirementService = Depends(get_requirement_service),
):
    return success_payload(
        await service.list_project(user_id, project_id, sprint_id, page, page_size)
    )


async def update_requirement(
    requirement_id: str,
    body: UpdateRequirementRequest,
    user_id: str = Depends(get_current_user_id),
    service: RequirementService = Depends(get_requirement_service),
):
    return success_payload(await service.update(user_id, requirement_id, body))


async def download_requirement_document(
    requirement_id: str,
    accept: str = Header(default=""),
    user_id: str = Depends(get_current_user_id),
    service: RequirementService = Depends(get_requirement_service),
):
    requirement = await service.get_download(user_id, requirement_id)
    ticket = await service.files.download(user_id, requirement.document_file_id)
    if "application/json" in accept:
        return JSONResponse(ticket, headers={"Cache-Control": "no-store"})
    return RedirectResponse(ticket["url"], status_code=307, headers={"Cache-Control": "no-store"})


async def delete_requirement(
    requirement_id: str,
    user_id: str = Depends(get_current_user_id),
    service: RequirementService = Depends(get_requirement_service),
):
    return success_payload(await service.delete(user_id, requirement_id))
