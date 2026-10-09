"""禅道新建 Bug 导入的候选、预览与导入契约。"""

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from testing_agent.core.enums import BugPriority, BugSeverity


class ZentaoBugCandidateItem(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    remote_bug_id: int = Field(gt=0)
    title: str
    status: str
    severity: str = ""
    priority: str = ""
    assigned_to: str = ""
    opened_by: str = ""
    opened_date: str = ""
    execution: int = 0
    story: int = 0
    linked: bool = False


class ZentaoBugPendingItem(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    field: str
    reason: str


class ZentaoBugImportPreview(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    remote_bug_id: int
    state: str  # ready / pending / pending_files / invalid
    title: str = ""
    snapshot: dict = Field(default_factory=dict)
    converted: dict = Field(default_factory=dict)
    description: dict = Field(default_factory=dict)
    pending: list[ZentaoBugPendingItem] = Field(default_factory=list)
    error_message: str = ""


class ZentaoBugImportPreviewRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    remote_bug_ids: list[int] = Field(min_length=1, max_length=20)


class ZentaoBugImportItemRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    remote_bug_id: int = Field(gt=0)
    assignee_user_id: str = Field(min_length=1, max_length=64)
    found_sprint_id: str = Field(min_length=1, max_length=64)
    requirement_id: str = Field(default="", max_length=64)
    severity: str = Field(default="", max_length=20)
    priority: str = Field(default="", max_length=20)

    @field_validator("severity")
    @classmethod
    def severity_override(cls, value: str) -> str:
        if value and value not in BugSeverity.values():
            raise ValueError("严重程度不合法")
        return value

    @field_validator("priority")
    @classmethod
    def priority_override(cls, value: str) -> str:
        if value and value not in BugPriority.values():
            raise ValueError("优先级不合法")
        return value


class ZentaoBugImportRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    request_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9:-]+$")
    items: list[ZentaoBugImportItemRequest] = Field(min_length=1, max_length=20)


class ZentaoBugImportResult(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    remote_bug_id: int
    status: str  # success / already_linked / conflict / failed
    bug_id: str = ""
    bug_no: int = 0
    title: str = ""
    error_message: str = ""
    pending: list[ZentaoBugPendingItem] = Field(default_factory=list)


class ZentaoBugImportPreviewResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    items: list[ZentaoBugImportPreview]


class ZentaoBugImportResponse(BaseModel):
    items: list[ZentaoBugImportResult]
