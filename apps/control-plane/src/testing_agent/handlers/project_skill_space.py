from __future__ import annotations

from fastapi import Depends
from fastapi.responses import Response

from testing_agent.api.deps import get_current_user_id, get_project_skill_space_service
from testing_agent.core.errors import success_payload
from testing_agent.core.object_storage import download_disposition
from testing_agent.schemas.project_skill_space import ProjectSkillUploadRequest
from testing_agent.services.common import list_payload
from testing_agent.services.project_skill_space import ProjectSkillSpaceService


async def list_project_skills(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ProjectSkillSpaceService = Depends(get_project_skill_space_service),
):
    payload = await service.list(project_id, user_id)
    if isinstance(payload, list):
        payload = list_payload(payload)
    return success_payload(payload)


async def create_project_skill(
    project_id: str,
    body: ProjectSkillUploadRequest,
    user_id: str = Depends(get_current_user_id),
    service: ProjectSkillSpaceService = Depends(get_project_skill_space_service),
):
    return success_payload(await service.upload(project_id, body, user_id))


async def delete_project_skill(
    project_id: str,
    skill_space_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ProjectSkillSpaceService = Depends(get_project_skill_space_service),
):
    return success_payload(await service.delete(project_id, skill_space_id, user_id))


async def download_project_skill(
    project_id: str,
    skill_space_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ProjectSkillSpaceService = Depends(get_project_skill_space_service),
):
    filename, content = await service.download_zip(project_id, skill_space_id, user_id)
    return Response(
        content,
        media_type="application/zip",
        headers={
            "Content-Disposition": download_disposition(filename),
            "Cache-Control": "no-store",
        },
    )
