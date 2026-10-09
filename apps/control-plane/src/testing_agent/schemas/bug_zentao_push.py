from datetime import datetime
from typing import Annotated, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from testing_agent.schemas.integration_job import IntegrationJobSummary


class BugZentaoPushTarget(TypedDict, total=False):
    project: int
    execution: int
    story: int
    projectName: str
    executionName: str
    storyName: str
    mcpServiceId: str
    mcpName: str
    instanceUrl: str


class BugZentaoPushResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    status: str = "not_pushed"
    source: str = "push"
    ready: bool = False
    execution_mode: str = "worker"
    active_job: IntegrationJobSummary | None = None
    latest_job: IntegrationJobSummary | None = None
    mcp_service_id: str = ""
    reason: str = ""
    remote_bug_id: int | None = None
    target: BugZentaoPushTarget = Field(default_factory=BugZentaoPushTarget)
    error_message: str = ""
    attachment_status: str = "none"
    description_status: str = "none"
    actor_user_id: str = ""
    updated_at: datetime | None = None
    opened_build: list[str] = Field(default_factory=lambda: ["trunk"])
    assigned_to: str = ""
    field_update_status: str = "none"
    field_update_error: str = ""
    warnings: list[str] = Field(
        default_factory=lambda: [
            "推送标题、描述、正文图片、严重程度、优先级和附件；"
            "新建时使用所选影响版本和禅道指派人，状态暂不随本次推送。",
            "已关联 Bug 补传附件和正文图片时，保留禅道已有影响版本和指派人。",
        ]
    )


class BugZentaoPushRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    opened_build: list[Annotated[str, Field(strict=True, pattern=r"^(trunk|[1-9][0-9]*)$")]] = (
        Field(default_factory=lambda: ["trunk"], min_length=1, max_length=50)
    )
    assigned_to: str = Field(default="", strict=True, max_length=100, pattern=r"^[^\s\x00-\x1f]*$")
    expected_target: BugZentaoPushTarget | None = None

    @field_validator("opened_build")
    @classmethod
    def validate_builds(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("影响版本不能重复")
        if "trunk" in value and len(value) > 1:
            raise ValueError("主干不能与其他影响版本同时选择")
        if any(build != "trunk" and int(build) > 2_147_483_647 for build in value):
            raise ValueError("影响版本编号不合法")
        return value


class BugZentaoBuildOption(BaseModel):
    id: str
    name: str


class BugZentaoUserOption(BaseModel):
    account: str
    name: str


class BugZentaoPushOptionsResponse(BaseModel):
    target: BugZentaoPushTarget
    builds: list[BugZentaoBuildOption]
    users: list[BugZentaoUserOption]
    current: "BugZentaoCurrentFields | None" = None


class BugZentaoCurrentFields(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    remote_bug_id: int
    opened_build: list[str]
    assigned_to: str


class BugZentaoUpdateRequest(BugZentaoPushRequest):
    opened_build: list[Annotated[str, Field(strict=True, pattern=r"^(trunk|[1-9][0-9]*)$")]] = (
        Field(min_length=1, max_length=50)
    )
    assigned_to: str = Field(strict=True, max_length=100, pattern=r"^[^\s\x00-\x1f]*$")
    expected_target: BugZentaoPushTarget
    expected_remote_bug_id: int = Field(gt=0)
    expected_opened_build: list[str] = Field(min_length=1, max_length=50)
    expected_assigned_to: str = Field(max_length=100)


class BugZentaoReconcileRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    remote_bug_id: int = Field(gt=0)


class BugZentaoAttachmentReconcileRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    remote_file_id: int = Field(gt=0)
