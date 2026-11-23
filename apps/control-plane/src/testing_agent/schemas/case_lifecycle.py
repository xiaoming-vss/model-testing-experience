from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class CaseInvalidationResponse(BaseModel):
    case_ids: list[str]
    updated_count: int

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CaseInvalidationRequest(BaseModel):
    """批量标记或恢复用例失效；只通过项目级状态接口修改。"""

    case_ids: list[str] = Field(min_length=1, max_length=500)
    invalidated: bool

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    @field_validator("case_ids")
    @classmethod
    def normalize_case_ids(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for case_id in value:
            item = str(case_id or "").strip()
            if not item:
                raise ValueError("caseIds 不能包含空值")
            if item not in seen:
                seen.add(item)
                normalized.append(item)
        return normalized
