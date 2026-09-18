from __future__ import annotations

# ruff: noqa: F401
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UpdateProjectRequest(BaseModel):
    name: str | None = None
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    description: str | None = None


class ProjectResponse(BaseModel):
    role: str = "owner"
    permissions: list[str] = Field(default_factory=list)
    project_id: str = Field()
    user_id: str = Field()
    name: str
    description: str = ""
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)
