from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ResourceBindingRequest(BaseModel):
    instance_url: str = ""
    provider: Literal["zentao", "gitlab"]
    # Choose a personal connection; instanceUrl can select an unambiguous personal connection.
    connection_id: str = Field(default="")
    remote_resource_type: str = Field(default="")
    remote_resource_id: str = Field()
    remote_parent_id: str = Field(default="")
    remote_name_snapshot: str = Field(default="")
    extra_json: Any | None = Field(default=None)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UpdateResourceBindingRequest(BaseModel):
    remote_resource_id: str | None = None
    """所有者使用本人同实例连接重新验证关联，不共享或转移凭据。"""

    connection_id: str = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UpdateRequirementBindingRequest(BaseModel):
    remote_resource_id: str | None = None
    """需求级 GitLab 仓库绑定更新:分支与基线分支(可选,未传字段保持不变)。"""

    connection_id: str = ""
    branch: str | None = Field(default=None)
    baseline_branch: str | None = Field(default=None)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ResourceBindingResponse(BaseModel):
    instance_url: str = ""
    binding_id: str = Field()
    provider: str
    connection_id: str = Field()
    local_resource_type: str = Field()
    local_resource_id: str = Field()
    remote_resource_type: str = Field()
    remote_resource_id: str = Field()
    remote_parent_id: str = Field(default="")
    remote_name_snapshot: str = Field(default="")
    status: str
    bound_at: datetime | str | None = Field(default=None)
    last_verified_at: datetime | str | None = Field(default=None)
    branch: str = Field(default="")
    baseline_branch: str = Field(default="")
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
