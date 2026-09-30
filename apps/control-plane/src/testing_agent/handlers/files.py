from fastapi import Depends
from fastapi.responses import JSONResponse

from testing_agent.api.deps import get_current_user_id, get_file_service
from testing_agent.core.config import Settings, get_settings
from testing_agent.core.errors import success_payload
from testing_agent.schemas.stored_file import FileUploadRequest
from testing_agent.services.stored_file import StoredFileService


async def capabilities(
    user_id: str = Depends(get_current_user_id), settings: Settings = Depends(get_settings)
):
    return success_payload({"enabled": settings.s3.enabled, "maxBytes": settings.s3.max_bytes})


async def upload(
    body: FileUploadRequest,
    user_id: str = Depends(get_current_user_id),
    service: StoredFileService = Depends(get_file_service),
):
    return JSONResponse(
        success_payload(await service.initiate(user_id, body)),
        headers={"Cache-Control": "no-store"},
    )


async def complete(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
    service: StoredFileService = Depends(get_file_service),
):
    return success_payload(await service.complete(user_id, file_id))


async def download(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
    service: StoredFileService = Depends(get_file_service),
):
    return JSONResponse(
        success_payload(await service.download(user_id, file_id)),
        headers={"Cache-Control": "no-store"},
    )


async def metadata(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
    service: StoredFileService = Depends(get_file_service),
):
    return success_payload(await service.metadata(user_id, file_id))
