from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


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
