from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ProjectSkillSpaceResponse(BaseModel):
    skill_space_id: str = Field()
    project_id: str = Field()
    version: int = 0
    hash: str = ""
    download_url: str = Field(default="")
    filename: str = ""
    size: int = 0
    is_default: bool = Field(default=False)
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ProjectSkillSyncResponse(BaseModel):
    project_id: str = Field()
    status: str

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
