from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from testing_agent.schemas.common import StrictRequest


class CreateZentaoIntegrationConnectionRequest(StrictRequest):
    project_id: str = Field(default="")
    name: str
    base_url: str = Field()
    allow_http: bool = False
    insecure_skip_verify: bool = False
    account: str
    password: str

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UpdateZentaoIntegrationConnectionRequest(StrictRequest):
    name: str | None = None
    base_url: str | None = Field(default=None)
    allow_http: bool | None = None
    insecure_skip_verify: bool | None = None
    account: str | None = None
    password: str | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CreateGitLabIntegrationConnectionRequest(StrictRequest):
    name: str
    base_url: str = Field()
    allow_http: bool = False
    insecure_skip_verify: bool = False
    access_token: str = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UpdateGitLabIntegrationConnectionRequest(StrictRequest):
    name: str | None = None
    base_url: str | None = Field(default=None)
    allow_http: bool | None = None
    insecure_skip_verify: bool | None = None
    access_token: str | None = Field(default=None)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CreateLLMIntegrationConnectionRequest(StrictRequest):
    project_id: str = Field(default="")
    name: str
    base_url: str = Field()
    model_id: str = Field()
    api_key: str = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UpdateLLMIntegrationConnectionRequest(StrictRequest):
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
    allow_http: bool = False
    insecure_skip_verify: bool = False
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


class GitLabResourceListResponse(BaseModel):
    connection_id: str = Field()
    group_id: str | None = Field(default=None)
    repository_id: str | None = Field(default=None)
    items: list[Any]
    total: int = 0

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
