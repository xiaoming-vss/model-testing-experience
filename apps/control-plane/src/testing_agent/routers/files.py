from fastapi import APIRouter

from testing_agent.handlers.files import capabilities, complete, download, metadata, upload
from testing_agent.schemas.common import ApiResponse
from testing_agent.schemas.stored_file import (
    FileCapabilities,
    FileCompletion,
    FileDownloadTicket,
    FileMetadata,
    FileUploadTicket,
)

router = APIRouter(prefix="/files", tags=["Files"])
router.get("/capabilities", response_model=ApiResponse[FileCapabilities])(capabilities)
router.post("/uploads", response_model=ApiResponse[FileUploadTicket])(upload)
router.post("/{file_id}/complete", response_model=ApiResponse[FileCompletion])(complete)
router.get("/{file_id}/download", response_model=ApiResponse[FileDownloadTicket])(download)
router.get("/{file_id}", response_model=ApiResponse[FileMetadata])(metadata)
