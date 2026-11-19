from __future__ import annotations

# ruff: noqa: F401
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from testing_agent.schemas.common import StrictRequest


class CreateProjectRequest(StrictRequest):
    name: str
    description: str = ""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UpdateProjectRequest(StrictRequest):
    """PATCH 语义：缺省保持原值；null 拒绝；描述空串表示清空。"""

    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    @field_validator("name", "description")
    @classmethod
    def reject_null(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("字段不能为 null；省略表示保持原值")
        return value


class ProjectResponse(BaseModel):
    role: str = "owner"
    permissions: list[str] = Field(default_factory=list)
    is_super_admin: bool = False
    project_id: str = Field()
    user_id: str = Field()
    name: str
    description: str = ""
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)
