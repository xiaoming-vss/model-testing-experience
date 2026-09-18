from __future__ import annotations

from pathlib import Path

from fastapi import Depends, File, Form, UploadFile
from fastapi.responses import FileResponse, Response

from testing_agent.api.deps import get_current_user_id, get_project_skill_space_service
from testing_agent.core.errors import success_payload
from testing_agent.services.common import list_payload
from testing_agent.services.project_skill_space import ProjectSkillSpaceService, dump_skill


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
    file: UploadFile = File(...),
    public_base_url: str = Form(default="", alias="publicBaseURL"),
    user_id: str = Depends(get_current_user_id),
    service: ProjectSkillSpaceService = Depends(get_project_skill_space_service),
):
    return success_payload(
        await service.upload(
            project_id,
            file.filename or "skills.zip",
            await file.read(),
            public_base_url,
            user_id,
        )
    )


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
    service: ProjectSkillSpaceService = Depends(get_project_skill_space_service),
):
    skill = await service.get_download_public(project_id, skill_space_id)
    path = Path(skill.storage_path)
    if skill.storage_path and path.exists() and path.is_file():
        return FileResponse(path, filename=skill.filename)
    content = getattr(skill, "content", None)
    if content is not None:
        return Response(
            content=content,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{skill.filename}"'},
        )
    return success_payload(dump_skill(skill))
