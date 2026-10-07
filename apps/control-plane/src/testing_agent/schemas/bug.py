from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


def _strip_title(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("title must not be empty")
    return value


class BugCreateRequest(BaseModel):
    """创建 Bug：责任人、严重程度、优先级、发现迭代为必填项。"""

    title: str
    description_html: str = Field(default="")
    assignee_user_id: str = Field(default="")
    severity: str = Field(default="normal")
    priority: str = Field(default="medium")
    found_sprint_id: str = Field(default="")
    planned_fix_sprint_id: str = Field(default="")
    requirement_id: str = Field(default="")
    attachment_file_ids: list[str] = Field(default_factory=list)
    source_order_id: str = Field(default="")
    source_entry_id: str = Field(default="")
    source_case_id: str = Field(default="")
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _strip_title(value)

    @field_validator("attachment_file_ids")
    @classmethod
    def validate_file_ids(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value.strip()))


class BugUpdateRequest(BaseModel):
    """编辑基本信息与描述；字段值为空串表示清空（计划修复迭代/所属需求）。"""

    title: str | None = None
    description_html: str | None = None
    severity: str | None = None
    priority: str | None = None
    planned_fix_sprint_id: str | None = None
    requirement_id: str | None = None
    attachment_file_ids: list[str] | None = None
    removed_attachment_file_ids: list[str] = Field(default_factory=list)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        return None if value is None else _strip_title(value)


class BugTransitionRequest(BaseModel):
    """确认、解决、关闭、激活；旧 rejectReason 仅用于兼容旧动作。"""

    action: str
    content: str = Field(default="")
    reject_reason: str = Field(default="")
    resolution: str = Field(default="", max_length=20)
    resolved_build: str = Field(default="", max_length=255)
    duplicate_bug: int = Field(default=0, ge=0, strict=True)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class BugTransferRequest(BaseModel):
    """独立转派操作：只更换责任人，不改变状态。"""

    assignee_user_id: str
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class BugCommentRequest(BaseModel):
    content: str
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must not be empty")
        return value


class BugAttachmentResponse(BaseModel):
    file_id: str = Field()
    filename: str = Field(default="")
    size: int = Field(default=0)
    content_type: str = Field(default="")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)


class BugMemberOption(BaseModel):
    user_id: str
    name: str
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class BugSprintOption(BaseModel):
    sprint_id: str
    name: str
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class BugOptionsResponse(BaseModel):
    members: list[BugMemberOption]
    sprints: list[BugSprintOption]


class BugResponse(BaseModel):
    id: int
    bug_id: str = Field()
    bug_no: int = Field(default=0)
    project_id: str = Field()
    title: str
    description_html: str = Field(default="")
    status: str = Field(default="")
    confirmed: bool = Field(default=False)
    resolution: str = Field(default="")
    resolved_build: str = Field(default="")
    duplicate_bug: int = Field(default=0)
    activated_count: int = Field(default=0)
    severity: str = Field(default="")
    priority: str = Field(default="")
    reporter_user_id: str = Field(default="")
    assignee_user_id: str = Field(default="")
    found_sprint_id: str = Field(default="")
    planned_fix_sprint_id: str = Field(default="")
    requirement_id: str = Field(default="")
    requirement_name: str = Field(default="")
    source_order_id: str = Field(default="")
    source_entry_id: str = Field(default="")
    source_case_id: str = Field(default="")
    source_order_name: str = Field(default="")
    source_case_title: str = Field(default="")
    attachments: list[BugAttachmentResponse] = Field(default_factory=list)
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)


class BugFieldChange(BaseModel):
    """字段修改记录：from/to 为展示用文本（截断）。"""

    field: str = Field(default="")
    from_value: str = Field(default="", alias="from")
    to_value: str = Field(default="", alias="to")
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class BugActivityFileRef(BaseModel):
    file_id: str = Field(default="")
    filename: str = Field(default="")
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class BugActivityDetail(BaseModel):
    """动态的结构化补充；不同 kind 只填相关字段，其余留默认。"""

    reject_reason: str = Field(default="")
    reject_reason_label: str = Field(default="")
    from_confirmed: bool | None = None
    to_confirmed: bool | None = None
    from_resolution: str = ""
    to_resolution: str = ""
    resolved_build: str = ""
    duplicate_bug: int = 0
    from_user_id: str = Field(default="")
    to_user_id: str = Field(default="")
    changes: list[BugFieldChange] = Field(default_factory=list)
    added_files: list[BugActivityFileRef] = Field(default_factory=list)
    removed_files: list[BugActivityFileRef] = Field(default_factory=list)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class BugActivityResponse(BaseModel):
    activity_id: str = Field()
    bug_id: str = Field()
    kind: str = Field(default="")
    actor_user_id: str = Field(default="")
    action: str = Field(default="")
    from_status: str = Field(default="")
    to_status: str = Field(default="")
    content: str = Field(default="")
    detail: BugActivityDetail = Field(default_factory=BugActivityDetail)
    created_at: datetime | str | None = Field(default="")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)
