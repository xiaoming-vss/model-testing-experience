from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ApiAppRepositoryRequest(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    group_id: str = Field(min_length=1, max_length=120)
    repository_id: str = Field(min_length=1, max_length=120)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class ApiAppCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=512)
    base_path: str = Field(default="", max_length=512)
    repository: ApiAppRepositoryRequest | None = None
    enabled: bool = True

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class ApiAppUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=512)
    base_path: str | None = Field(default=None, max_length=512)
    repository: ApiAppRepositoryRequest | None = None
    enabled: bool | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class ApiAppRepositoryResponse(BaseModel):
    project_id: str = Field(default="")
    path: str = Field(default="")
    name: str = Field(default="")
    instance_url: str = Field(default="")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiAppResponse(BaseModel):
    app_id: str
    project_id: str
    name: str
    description: str = ""
    base_path: str = ""
    repository: ApiAppRepositoryResponse | None = None
    enabled: bool = True
    interface_count: int = 0
    enabled_interface_count: int = 0
    version: int = 1
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)
