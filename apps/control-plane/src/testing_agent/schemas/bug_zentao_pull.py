"""已关联 Bug 从禅道拉取更新的预览与应用契约。"""

from pydantic import BaseModel, ConfigDict, Field, field_validator
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


class ZentaoRemoteGroupPreview(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    group: str
    state: str
    local: dict = Field(default_factory=dict)
    remote: dict = Field(default_factory=dict)
    baseline: dict | None = None
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
