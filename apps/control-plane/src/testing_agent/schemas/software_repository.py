from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class SoftwareRepositoryPayload(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    group_id: str = Field(min_length=1, max_length=120)
    repository_id: str = Field(min_length=1, max_length=120)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class SoftwareRepositoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=512)
    base_path: str = Field(default="", max_length=512)
    repository: SoftwareRepositoryPayload

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class SoftwareRepositoryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=512)
    base_path: str | None = Field(default=None, max_length=512)
    repository: SoftwareRepositoryPayload | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class SoftwareRepositoryGitRepositoryResponse(BaseModel):
    project_id: str = Field(default="")
    path: str = Field(default="")
    name: str = Field(default="")
    instance_url: str = Field(default="")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SoftwareRepositoryResponse(BaseModel):
    software_repository_id: str
    project_id: str
    name: str
    description: str = ""
    base_path: str = ""
    repository: SoftwareRepositoryGitRepositoryResponse | None = None
    interface_groups: list[str] = Field(default_factory=list)
    interface_count: int = 0
    version: int = 1
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)
