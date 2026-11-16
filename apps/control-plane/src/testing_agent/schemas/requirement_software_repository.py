from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from testing_agent.schemas.software_repository import SoftwareRepositoryGitRepositoryResponse


class RequirementSoftwareRepositoryCreateRequest(BaseModel):
    software_repository_id: str = Field(min_length=1, max_length=64)
    branch: str = Field(min_length=1, max_length=255)
    baseline_branch: str = Field(min_length=1, max_length=255)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class RequirementSoftwareRepositoryUpdateRequest(BaseModel):
    branch: str | None = Field(default=None, min_length=1, max_length=255)
    baseline_branch: str | None = Field(default=None, min_length=1, max_length=255)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class RequirementSoftwareRepositoryResponse(BaseModel):
    requirement_id: str
    software_repository_id: str
    software_repository_name: str
    base_path: str = ""
    repository: SoftwareRepositoryGitRepositoryResponse | None = None
    branch: str
    baseline_branch: str
    created_by_user_id: str = ""
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
