from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class FileUploadRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    project_id: str
    filename: str = Field(min_length=1, max_length=255, pattern=r"^[^/\\\x00-\x1f]+$")
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    purpose: Literal[
        "requirement", "attachment", "ui_source_archive", "project_skill", "ui_artifact"
    ] = "attachment"


class FileData(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class FileCapabilities(FileData):
    enabled: bool
    max_bytes: int


class SignedPost(FileData):
    url: str
    fields: dict[str, str]


class FileUploadTicket(FileData):
    file_id: str
    upload: SignedPost
    expires_in: int


class FileCompletion(FileData):
    file_id: str
    status: str


class FileDownloadTicket(FileData):
    url: str
    filename: str
    size: int
    sha256: str
    expires_in: int


class FileMetadata(FileCompletion):
    project_id: str
    filename: str
    content_type: str
    size: int
    sha256: str
    uploaded_by: str
    created_at: datetime
    completed_at: datetime | None
