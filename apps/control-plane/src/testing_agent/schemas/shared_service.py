from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

Provider = Literal["llm", "zentao", "gitlab"]


class ServiceCreate(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1, max_length=512)
    model_id: str = Field(default="", max_length=255)


class ServiceRename(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)


class PersonalAuthorizationRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    api_key: str | None = Field(default=None, min_length=1)
    access_token: str | None = Field(default=None, min_length=1)
    account: str | None = Field(default=None, min_length=1)
    password: str | None = Field(default=None, min_length=1)


class MyAuthorization(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    status: str = "unauthorized"
    connection_id: str | None = None
    account: str = ""
    last_auth_at: datetime | None = None


class SharedServiceResponse(ServiceCreate):
    service_id: str
    project_id: str
    provider: Provider
    authorization: MyAuthorization
