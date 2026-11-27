from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from testing_agent.schemas.common import StrictRequest


class FileUploadRequest(StrictRequest):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    project_id: str
    filename: str = Field(min_length=1, max_length=255, pattern=r"^[^/\\\x00-\x1f]+$")
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    purpose: Literal[
        "requirement", "attachment", "project_skill", "ui_artifact", "perf_case_data"
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
