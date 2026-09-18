"""迭代代码变更概览响应结构(工单 08,RC-6)。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class SprintCodeOverviewRepositoryResponse(BaseModel):
    """迭代代码概览单仓库条目。"""

    instance_url: str = ""
    repository_id: str = Field()
    name: str = ""
    group_id: str = Field(default="")
    branch: str = ""
    baseline_ref: str | None = Field(default=None)
    baseline_note: str = Field(default="")
    is_new_repository: bool = Field(default=False)
    commits_count: int = Field(default=0)
    additions: int = 0
    deletions: int = 0
    error: str = ""
    remediation: str = ""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SprintCodeOverviewResponse(BaseModel):
    sprint_id: str = Field()
    project_id: str = Field()
    generated_at: str = Field()
    repositories: list[SprintCodeOverviewRepositoryResponse] = []
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
