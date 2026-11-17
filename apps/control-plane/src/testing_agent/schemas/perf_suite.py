from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from testing_agent.schemas.perf_case import PerfCaseSummaryResponse


class PerfSuiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=512)
    enabled: bool = True

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class PerfSuiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=512)
    enabled: bool | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class PerfSuiteCaseOrderUpdate(BaseModel):
    case_ids: list[str] = Field(min_length=1)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class PerfSuiteCaseResponse(PerfCaseSummaryResponse):
    yaml: str = ""


class PerfSuiteSummaryResponse(BaseModel):
    suite_id: str
    project_id: str
    name: str
    description: str
    enabled: bool
    case_count: int = 0
    enabled_case_count: int = 0
    step_count: int = 0
    data_file_count: int = 0
    load_models: list[str] = Field(default_factory=list)
    last_run_status: str = ""
    last_run_outcome: str = ""
    created_at: datetime | str | None = ""
    updated_at: datetime | str | None = ""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PerfSuiteResponse(PerfSuiteSummaryResponse):
    cases: list[PerfSuiteCaseResponse] = Field(default_factory=list)
    created_by: str = ""
