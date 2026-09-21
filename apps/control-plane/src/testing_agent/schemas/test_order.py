from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from testing_agent.domain.function_case_content import CaseContent
from testing_agent.schemas.ai_generate_task import AiGenerateTaskRunResponse


class TestOrderRequest(BaseModel):
    name: str
    tested_version: str = Field(default="")
    # 可选：从另一张测试单带入结果非「通过」的条目（重测）。
    source_order_id: str = Field(default="")
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TestOrderUpdateRequest(BaseModel):
    name: str | None = None
    tested_version: str | None = None
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TestOrderResponse(BaseModel):
    order_id: str = Field()
    project_id: str = Field()
    sprint_id: str = Field()
    name: str
    tested_version: str = Field(default="")
    entries_total: int = Field(default=0)
    entries_executed: int = Field(default=0)
    entries_passed: int = Field(default=0)
    entries_failed: int = Field(default=0)
    entries_blocked: int = Field(default=0)
    entries_skipped: int = Field(default=0)
    status: str = Field(default="")
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)


class TestOrderEntryResponse(BaseModel):
    entry_id: str = Field()
    order_id: str = Field()
    case_type: str = Field(default="function")
    case_id: str = Field()
    case_title: str = Field(default="")
    case_module: str = Field(default="")
    case_priority: str = Field(default="")
    order_no: int = Field(default=0)
    status: str = Field(default="")
    assignee_user_id: str = Field(default="")
    actual_results: str = Field(default="")
    failure_reason: str = Field(default="")
    block_reason: str = Field(default="")
    zentao_bug_id: str = Field(default="")
    executor_user_id: str = Field(default="")
    executed_at: datetime | str | None = Field(default=None)
    snapshot: CaseContent | None = None
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)


class TestOrderEntryUpdateRequest(BaseModel):
    """执行结果的即时保存：针对整条用例的结论、实际结果与原因。"""

    status: str | None = None
    actual_results: str | None = None
    failure_reason: str | None = None
    block_reason: str | None = None
    zentao_bug_id: str | None = None
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TestOrderAddCasesRequest(BaseModel):
    case_ids: list[str] = Field(min_length=1, max_length=500)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    @field_validator("case_ids")
    @classmethod
    def validate_ids(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("caseIds must contain non-empty IDs")
        return list(dict.fromkeys(values))


class TestOrderAssignRequest(BaseModel):
    entry_ids: list[str] = Field(min_length=1, max_length=500)
    # 空串表示取消分配。
    assignee_user_id: str = Field(default="")
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    @field_validator("entry_ids")
    @classmethod
    def validate_ids(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("entryIds must contain non-empty IDs")
        return list(dict.fromkeys(values))


class TestOrderEntriesBatchMarkRequest(BaseModel):
    entry_ids: list[str] = Field(min_length=1, max_length=500)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    @field_validator("entry_ids")
    @classmethod
    def validate_ids(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("entryIds must contain non-empty IDs")
        return list(dict.fromkeys(values))


class TestOrderEntriesBatchMarkResponse(BaseModel):
    marked_count: int
    skipped_count: int
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TestOrderAddCasesResponse(BaseModel):
    added_count: int
    skipped_count: int
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TestOrderGraphRequest(BaseModel):
    """图谱输入由外部接口组装，平台原样转发，不改内部字段名。

    字段类型保持 `Any`：图谱输入是外部接口的契约，结构由 `require_graph_input` 校验，
    这里不声明成字典，避免 OpenAPI 里出现无意义的 additionalProperties 占位。
    """

    graph_input: Any = Field(default_factory=dict)
    connection_id: str = Field(default="")
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TestOrderGraphResponse(BaseModel):
    """最近一次图谱 run；从未生成过时 run 为 null。"""

    order_id: str = Field()
    run: AiGenerateTaskRunResponse | None = Field(default=None)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TestOrderGraphInputRequirement(BaseModel):
    requirement_id: str
    requirement_title: str
    requirement_content: str


class TestOrderGraphInputCase(BaseModel):
    case_id: str
    case_module: str
    case_title: str
    case_type: str
    priority: str
    precondition: list[str]
    test_steps: list[str]
    expected_results: list[str]


class TestOrderGraphInputLink(BaseModel):
    """需求到用例的关联；`requirement_id` 为 null 表示这组用例没有绑定本迭代的需求。"""

    requirement_id: str | None
    case_ids: list[str]


class TestOrderGraphInputResponse(BaseModel):
    """测试单的图谱输入，可直接作为派发请求的 graphInput。

    字段名与 worker 侧 skill 的输入契约一致，保持 snake_case，勿加 camel 别名。
    """

    requirements: list[TestOrderGraphInputRequirement]
    cases: list[TestOrderGraphInputCase]
    case_requirement_links: list[TestOrderGraphInputLink]
