from __future__ import annotations

from pathlib import Path

from fastapi import Depends, File, Form, UploadFile
from fastapi.responses import FileResponse, Response

from testing_agent.api.deps import get_current_user_id, get_requirement_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.requirement import CreateRequirementRequest, UpdateRequirementRequest
from testing_agent.services.requirement import RequirementDocumentFile, RequirementService


async def create_requirement(
    sprint_id: str,
    body: CreateRequirementRequest,
    user_id: str = Depends(get_current_user_id),
    service: RequirementService = Depends(get_requirement_service),
):
    return success_payload(await service.create(user_id, sprint_id, body))


async def create_requirement_from_file(
    sprint_id: str,
    name: str = Form(...),
    document_type: str = Form(default="docx", alias="documentType"),
    document_content: str = Form(default="", alias="documentContent"),
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    service: RequirementService = Depends(get_requirement_service),
):
    body = CreateRequirementRequest(
        name=name,
        document_type=document_type,
        document_content="",
    )
    return success_payload(
        await service.create(
            user_id,
            sprint_id,
            body,
            RequirementDocumentFile(
                filename=file.filename or "requirement",
                content=await file.read(),
            ),
        )
    )


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


async def update_requirement(
    requirement_id: str,
    body: UpdateRequirementRequest,
    user_id: str = Depends(get_current_user_id),
    service: RequirementService = Depends(get_requirement_service),
):
    return success_payload(await service.update(user_id, requirement_id, body))


async def upload_requirement_document(
    requirement_id: str,
    document_type: str | None = Form(default=None, alias="documentType"),
    document_content: str | None = Form(default=None, alias="documentContent"),
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    service: RequirementService = Depends(get_requirement_service),
):
    return success_payload(
        await service.upload_document(
            user_id,
            requirement_id,
            RequirementDocumentFile(
                filename=file.filename or "requirement",
                content=await file.read(),
            ),
            document_type,
            None,
        )
    )


async def download_requirement_document(
    requirement_id: str,
    user_id: str = Depends(get_current_user_id),
    service: RequirementService = Depends(get_requirement_service),
):
    requirement = await service.get_download(user_id, requirement_id)
    path = Path(requirement.document_storage_path)
    if requirement.document_storage_path and path.exists() and path.is_file():
        return FileResponse(
            path,
            filename=requirement.document_filename or "requirement",
            media_type="application/octet-stream",
        )
    content = getattr(requirement, "content", None)
    if content is not None:
        return Response(
            content=content,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{requirement.document_filename or "requirement"}"'
                )
            },
        )
    return Response(
        content=requirement.document_content.encode("utf-8"),
        media_type="application/octet-stream",
    )


async def delete_requirement(
    requirement_id: str,
    user_id: str = Depends(get_current_user_id),
    service: RequirementService = Depends(get_requirement_service),
):
    return success_payload(await service.delete(user_id, requirement_id))
