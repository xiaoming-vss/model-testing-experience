from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

ZENTAO_MCP_NAME = "ZenTao-MCP"

Provider = Literal["llm", "zentao", "gitlab", "mcp"]


class ServiceCreate(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1, max_length=512)
    model_id: str = Field(default="", max_length=255)
    template_id: Literal["zentao"] | None = None
    zentao_instance_url: str = Field(default="", max_length=512)


class ServiceRename(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    base_url: str | None = Field(default=None, min_length=1, max_length=512)
    zentao_instance_url: str | None = Field(default=None, max_length=512)
    confirm_instance_switch: bool = False


class PersonalAuthorizationRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    token: str | None = Field(default=None, min_length=1)
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


class McpInstanceReset(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    instance_url: str = Field(min_length=1, max_length=512)


class SharedServiceResponse(ServiceCreate):
    service_id: str
    project_id: str
    provider: Provider
    authorization: MyAuthorization
    zentao_api_base_url: str = ""
    instance_error: str = ""
    connection_status: str = "unchecked"
    instance_reset_required: bool = False
    pending_instance_url: str = ""


class McpTemplate(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    template_id: Literal["zentao"] = "zentao"
    name: str = ZENTAO_MCP_NAME
    type: Literal["streamableHttp"] = "streamableHttp"
    authorization_header: Literal["token"] = "token"
