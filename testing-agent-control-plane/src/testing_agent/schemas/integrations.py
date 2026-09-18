from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CreateZentaoIntegrationConnectionRequest(BaseModel):
    project_id: str = Field(default="")
    name: str
    base_url: str = Field()
    account: str
    password: str

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UpdateZentaoIntegrationConnectionRequest(BaseModel):
    name: str | None = None
    base_url: str | None = Field(default=None)
    account: str | None = None
    password: str | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CreateGitLabIntegrationConnectionRequest(BaseModel):
    name: str
    base_url: str = Field()
    access_token: str = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UpdateGitLabIntegrationConnectionRequest(BaseModel):
    name: str | None = None
    base_url: str | None = Field(default=None)
    access_token: str | None = Field(default=None)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CreateLLMIntegrationConnectionRequest(BaseModel):
    project_id: str = Field(default="")
    name: str
    base_url: str = Field()
    model_id: str = Field()
    api_key: str = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UpdateLLMIntegrationConnectionRequest(BaseModel):
    name: str | None = None
    base_url: str | None = Field(default=None)
    model_id: str | None = Field(default=None)
    api_key: str | None = Field(default=None)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class IntegrationConnectionResponse(BaseModel):
    connection_id: str = Field()
    project_id: str = Field(default="")
    provider: str
    name: str
    base_url: str = Field()
    auth_type: str = Field()
    account: str = ""
    status: str
    has_access_token: bool = Field()
    model_id: str = Field(default="")
    last_auth_at: datetime | str | None = Field(default=None)
    last_auth_error: str = Field(default="")
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class RemoteResourceListResponse(BaseModel):
    connection_id: str = Field()
    remote_project_id: str | None = Field(default=None)
    remote_execution_id: str | None = Field(default=None)
    items: list[Any]
    total: int = 0

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class GitLabResourceListResponse(BaseModel):
    connection_id: str = Field()
    group_id: str | None = Field(default=None)
    repository_id: str | None = Field(default=None)
    items: list[Any]
    total: int = 0

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
