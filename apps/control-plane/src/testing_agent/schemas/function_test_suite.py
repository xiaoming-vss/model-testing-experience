from __future__ import annotations

# ruff: noqa: F401
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class FunctionSuiteRequest(BaseModel):
    name: str
    description: str = ""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class FunctionSuiteUpdateRequest(BaseModel):
    name: str | None = None
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    description: str | None = None


class FunctionSuiteResponse(BaseModel):
    case_count: int = Field(default=0, ge=0)
    suite_id: str = Field()
    requirement_id: str = Field()
    name: str
    description: str = ""
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)


class FunctionSuiteRequirementItem(BaseModel):
    requirement_id: str
    requirement_title: str
    requirement_content: str


class FunctionSuiteCaseViewItem(BaseModel):
    case_id: str
    case_module: str
    case_title: str
    case_type: str
    priority: str
    precondition: list[str]
    test_steps: list[str]
    expected_results: list[str]


class FunctionSuiteCaseRequirementLink(BaseModel):
    requirement_id: str
    case_ids: list[str]


class FunctionSuiteCaseViewResponse(BaseModel):
    """测试集需求-用例视图：字段名保持生成侧契约的 snake_case，勿加 camel 别名。"""

    requirements: list[FunctionSuiteRequirementItem]
    cases: list[FunctionSuiteCaseViewItem]
    case_requirement_links: list[FunctionSuiteCaseRequirementLink]
