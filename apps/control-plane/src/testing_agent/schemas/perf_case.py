from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class PerfDataFile(BaseModel):
    file_id: str
    filename: str
    size: int
    sha256: str

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PerfCaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=512)
    yaml: str = Field(min_length=1)
    data_file_ids: list[str] = Field(default_factory=list, max_length=20)
    suite_id: str | None = None
    order_no: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class PerfCaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=512)
    yaml: str | None = Field(default=None, min_length=1)
    data_file_ids: list[str] | None = Field(default=None, max_length=20)
    enabled: bool | None = None
    order_no: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class PerfCaseSummaryResponse(BaseModel):
    case_id: str
    project_id: str
    suite_id: str = ""
    order_no: int = 0
    name: str
    description: str
    version: int
    enabled: bool
    data_files: list[PerfDataFile]
    created_at: datetime | str | None = ""
    updated_at: datetime | str | None = ""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PerfCaseResponse(PerfCaseSummaryResponse):
    yaml: str
    created_by: str
