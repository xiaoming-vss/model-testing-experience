"""已关联 Bug 从禅道拉取更新的预览与应用契约。"""

from datetime import datetime
from typing import TypedDict

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator
from pydantic.alias_generators import to_camel

FIELD_GROUPS = ("profile", "description", "status", "assignee")
GROUP_STATES = (
    "synced",
    "remote_changed",
    "local_changed",
    "conflict",
    "confirm_baseline",
    "pending_files",
    "pending_map",
    "manual",
)


class ZentaoGroupValues(TypedDict, total=False):
    """The selected group's fields; absence stays absent rather than becoming null."""

    title: str
    severity: str | None
    priority: str | None
    digest: str
    hasImages: bool
    hasContent: bool
    status: str
    confirmed: bool
    resolution: str
    resolvedBuild: str
    activatedCount: int
    userId: str
    account: str


class ZentaoGroupBaseline(TypedDict):
    # Historical snapshots are intentionally extensible JSON, not current command input.
    local: dict[str, JsonValue]
    remote: dict[str, JsonValue]
    appliedAt: datetime | None


class ZentaoRemoteGroupPreview(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    group: str
    state: str
    local: ZentaoGroupValues = Field(default_factory=ZentaoGroupValues)
    remote: ZentaoGroupValues = Field(default_factory=ZentaoGroupValues)
    baseline: ZentaoGroupBaseline | None = None
    reason: str = ""


class ZentaoRemotePreviewResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    remote_bug_id: int
    remote_digest: str
    linked_source: str
    groups: list[ZentaoRemoteGroupPreview]


class ZentaoPullGroupRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    group: str
    action: str  # apply_remote / keep_local
    assignee_user_id: str = Field(default="", max_length=64)
    severity: str = Field(default="", max_length=20)
    priority: str = Field(default="", max_length=20)

    @field_validator("group")
    @classmethod
    def known_group(cls, value: str) -> str:
        if value not in FIELD_GROUPS:
            raise ValueError("未知字段组")
        return value

    @field_validator("action")
    @classmethod
    def known_action(cls, value: str) -> str:
        if value not in {"apply_remote", "keep_local"}:
            raise ValueError("action 只能是 apply_remote 或 keep_local")
        return value


class ZentaoPullRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    remote_digest: str = Field(min_length=8, max_length=64)
    groups: list[ZentaoPullGroupRequest] = Field(min_length=1, max_length=len(FIELD_GROUPS))

    @field_validator("groups")
    @classmethod
    def unique_groups(cls, value: list[ZentaoPullGroupRequest]):
        if len({item.group for item in value}) != len(value):
            raise ValueError("字段组不能重复")
        return value


class ZentaoPullResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    applied: list[str] = Field(default_factory=list)
    kept: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
