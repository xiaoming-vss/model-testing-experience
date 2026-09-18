from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class TestMetricGroup(BaseModel):
    total: int = 0
    executed: int = 0
    pending: int = 0
    success: int = 0
    failed: int = 0
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class BugMetricGroup(BaseModel):
    total: int = 0
    resolved: int = 0
    closed: int = 0
    unresolved: int = 0
    fatal: int = 0
    serious: int = 0
    normal: int = 0
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    suggestion: int = 0


class ProjectMetricContext(BaseModel):
    project_name: str = Field(default="")
    description: str = ""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SprintMetricContext(BaseModel):
    sprint_name: str = Field(default="")
    start_date: str = Field(default="")
    end_date: str = Field(default="")
    description: str = ""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class RequirementMetricContext(BaseModel):
    requirement_name: str = Field(default="")
    description: str = ""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class BugDetailContext(BaseModel):
    title: str = ""
    module: str = ""
    severity: str = ""
    status: str = ""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    owner: str = ""
    description: str = ""


class SprintDailyMetricRequest(BaseModel):
    connection_id: str | None = None
    function_case_total: int | None = Field(default=None)
    function_case_executed: int | None = Field(default=None)
    function_case_pending: int | None = Field(default=None)
    function_case_success: int | None = Field(default=None)
    function_case_failed: int | None = Field(default=None)
    api_case_total: int | None = Field(default=None)
    api_case_executed: int | None = Field(default=None)
    api_case_pending: int | None = Field(default=None)
    api_case_success: int | None = Field(default=None)
    api_case_failed: int | None = Field(default=None)
    ui_case_total: int | None = Field(default=None)
    ui_case_executed: int | None = Field(default=None)
    ui_case_pending: int | None = Field(default=None)
    ui_case_success: int | None = Field(default=None)
    ui_case_failed: int | None = Field(default=None)
    bug_total: int | None = Field(default=None)
    bug_resolved: int | None = Field(default=None)
    bug_closed: int | None = Field(default=None)
    bug_unresolved: int | None = Field(default=None)
    bug_fatal: int | None = Field(default=None)
    bug_serious: int | None = Field(default=None)
    bug_normal: int | None = Field(default=None)
    bug_suggestion: int | None = Field(default=None)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SprintDailyMetricResponse(BaseModel):
    project_id: str = Field()
    sprint_id: str = Field()
    snapshot_date: str = Field()
    function: TestMetricGroup
    api: TestMetricGroup
    ui: TestMetricGroup
    bug: BugMetricGroup
    project: ProjectMetricContext = Field(default_factory=ProjectMetricContext)
    sprint: SprintMetricContext = Field(default_factory=SprintMetricContext)
    requirements: list[RequirementMetricContext] = Field(default_factory=list)
    bugs: list[BugDetailContext] = Field(default_factory=list)
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
