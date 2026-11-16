from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ApiInterfaceRow(BaseModel):
    enabled: bool = True
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(default="string")
    required: bool = False
    example: str = Field(default="", max_length=4096)
    description: str = Field(default="", max_length=512)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class ApiInterfaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    method: str = Field(min_length=1, max_length=10)
    path: str = Field(min_length=1, max_length=1024)
    description: str = Field(default="", max_length=1024)
    tags: list[str] = Field(default_factory=list, max_length=20)
    headers: list[ApiInterfaceRow] = Field(default_factory=list, max_length=200)
    path_params: list[ApiInterfaceRow] = Field(default_factory=list, max_length=200)
    query_params: list[ApiInterfaceRow] = Field(default_factory=list, max_length=200)
    body_type: Literal["none", "json", "form", "raw"] = "none"
    body_schema: Any | None = None
    body_example: Any | None = None
    body_text: str = Field(default="", max_length=20000)
    response_status: int = Field(default=200, ge=100, le=599)
    response_description: str = Field(default="", max_length=512)
    response_schema: Any | None = None
    response_example: Any | None = None
    requirement_ids: list[str] = Field(default_factory=list, max_length=50)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class ApiInterfaceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    method: str | None = Field(default=None, min_length=1, max_length=10)
    path: str | None = Field(default=None, min_length=1, max_length=1024)
    description: str | None = Field(default=None, max_length=1024)
    tags: list[str] | None = Field(default=None, max_length=20)
    headers: list[ApiInterfaceRow] | None = Field(default=None, max_length=200)
    path_params: list[ApiInterfaceRow] | None = Field(default=None, max_length=200)
    query_params: list[ApiInterfaceRow] | None = Field(default=None, max_length=200)
    body_type: Literal["none", "json", "form", "raw"] | None = None
    body_schema: Any | None = None
    body_example: Any | None = None
    body_text: str | None = Field(default=None, max_length=20000)
    response_status: int | None = Field(default=None, ge=100, le=599)
    response_description: str | None = Field(default=None, max_length=512)
    response_schema: Any | None = None
    response_example: Any | None = None
    requirement_ids: list[str] | None = Field(default=None, max_length=50)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class ApiInterfaceGroupRenameRequest(BaseModel):
    current_group_name: str = Field(min_length=1, max_length=50)
    new_group_name: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class ApiInterfaceGroupCreateRequest(BaseModel):
    group_name: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class ApiInterfaceGroupDeleteRequest(BaseModel):
    group_name: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class ApiInterfaceMoveGroupRequest(BaseModel):
    # 显式空字符串表示清除全部标签；省略字段必须被拒绝，不能当作清除信号。
    group_name: str = Field(max_length=50)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class ApiInterfaceGroupMutationResponse(BaseModel):
    group_name: str = ""
    new_group_name: str = ""
    updated_count: int = 0

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiInterfaceRequirementResponse(BaseModel):
    requirement_id: str
    name: str
    sprint_id: str
    sprint_name: str

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiInterfaceSourceResponse(BaseModel):
    type: str = "manual"
    name: str = ""
    url: str = ""
    version: str = ""
    imported_at: datetime | str | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiInterfaceResponse(BaseModel):
    interface_id: str
    software_repository_id: str
    software_repository_name: str = ""
    name: str
    method: str
    path: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    headers: list[ApiInterfaceRow] = Field(default_factory=list)
    path_params: list[ApiInterfaceRow] = Field(default_factory=list)
    query_params: list[ApiInterfaceRow] = Field(default_factory=list)
    body_type: str = "none"
    body_schema: Any | None = None
    body_example: Any | None = None
    body_text: str = ""
    response_status: int = 200
    response_description: str = ""
    response_schema: Any | None = None
    response_example: Any | None = None
    security: Any | None = None
    security_schemes: Any | None = None
    version: int = 1
    requirements: list[ApiInterfaceRequirementResponse] = Field(default_factory=list)
    source: ApiInterfaceSourceResponse = Field(default_factory=ApiInterfaceSourceResponse)
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiInterfaceListItem(BaseModel):
    interface_id: str
    software_repository_id: str
    software_repository_name: str = ""
    name: str
    method: str
    path: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    requirements: list[ApiInterfaceRequirementResponse] = Field(default_factory=list)
    source_type: str = "manual"
    updated_at: datetime | str | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
