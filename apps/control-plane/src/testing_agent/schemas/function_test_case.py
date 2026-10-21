from __future__ import annotations

# ruff: noqa: F401
import json
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from testing_agent.domain.function_case_content import CaseContent


class FunctionCaseRequest(BaseModel):
    content: CaseContent | None = None
    module: str = ""
    title: str
    preconditions: str = ""
    steps: str = ""
    expected_results: str = Field(default="")
    priority: str = ""
    case_type: str = Field(default="")
    order_no: int = Field(default=0)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class FunctionCaseUpdateRequest(BaseModel):
    content: CaseContent | None = None
    module: str | None = None
    title: str | None = None
    preconditions: str | None = None
    steps: str | None = None
    expected_results: str | None = Field(default=None)
    priority: str | None = None
    case_type: str | None = Field(default=None)
    order_no: int | None = Field(default=None)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class FunctionCaseResponse(FunctionCaseRequest):
    case_id: str = Field()
    suite_id: str = Field()
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)


class FunctionCaseLibraryItem(FunctionCaseResponse):
    """用例库条目：用例内容加上它所属的测试集 / 需求 / 迭代，供项目范围检索使用。"""

    suite_name: str = Field(default="")
    requirement_id: str = Field(default="")
    requirement_name: str = Field(default="")
    sprint_id: str = Field(default="")
    sprint_name: str = Field(default="")


class FunctionCaseImportResponse(BaseModel):
    imported: int
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CasePushOptions(BaseModel):
    restore_confirmed: bool = False
    request_id: str = Field(default_factory=lambda: uuid4().hex, min_length=1, max_length=64)
    # Missing means unresolved; 0 explicitly creates; positive explicitly binds a remote ID.
    choices: dict[str, Annotated[int, Field(strict=True, ge=0, le=2_147_483_647)]] = Field(
        default_factory=dict, max_length=10000
    )
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    @field_validator("choices")
    @classmethod
    def valid_choices(cls, value: dict[str, int]) -> dict[str, int]:
        if any(
            not key or identifier < 0 or identifier > 2_147_483_647
            for key, identifier in value.items()
        ):
            raise ValueError("choices 必须指定用例编号及有效远端编号，0 表示新建")
        return value


class ImportFunctionCasesToZentaoRequest(CasePushOptions):
    connection_id: str = Field(default="")
    product_id: int = Field(alias="productId", gt=0)
    case_ids: list[str] = Field(default_factory=list, max_length=10000)
    module_id: int = Field(default=0, ge=0)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ImportFunctionSuitesToZentaoRequest(CasePushOptions):
    connection_id: str = Field(default="")
    product_id: int = Field(gt=0)
    module_id: int = Field(default=0, ge=0)
    suite_ids: list[str] = Field(min_length=1, max_length=10000)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    @field_validator("suite_ids")
    @classmethod
    def validate_suite_ids(cls, value: list[str]) -> list[str]:
        normalized = [str(suite_id or "").strip() for suite_id in value]
        if any(not suite_id for suite_id in normalized):
            raise ValueError("suiteIds 不能为空")
        if len(set(normalized)) != len(normalized):
            raise ValueError("suiteIds 不能包含重复项")
        return normalized


class FunctionCaseZentaoImportItemResponse(BaseModel):
    operation_id: str | None = None
    case_id: str = Field()
    remote_case_id: int = Field()
    error_message: str | None = None
    status: str
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class FunctionCaseZentaoImportResponse(BaseModel):
    status: str = "success"
    suite_id: str = Field()
    product_id: int = Field()
    remote_project_id: int = Field()
    remote_execution_id: int = Field()
    imported_case_count: int = Field()
    items: list[FunctionCaseZentaoImportItemResponse]
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class FunctionSuiteZentaoImportItemResponse(BaseModel):
    items: list[FunctionCaseZentaoImportItemResponse] = Field(default_factory=list)
    suite_id: str = Field()
    status: Literal["success", "failed"]
    imported_case_count: int = Field()
    error_code: int | None = Field(default=None)
    error_message: str | None = Field(default=None)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class FunctionSuitesZentaoImportResponse(BaseModel):
    requirement_id: str = Field()
    status: Literal["success", "partial_failure", "failed"]
    total_suite_count: int = Field()
    succeeded_suite_count: int = Field()
    failed_suite_count: int = Field()
    imported_case_count: int = Field()
    items: list[FunctionSuiteZentaoImportItemResponse]
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class FunctionCasesBatchDeleteRequest(BaseModel):
    case_ids: list[str] = Field(min_length=1, max_length=500)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    @field_validator("case_ids")
    @classmethod
    def validate_ids(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("caseIds must contain non-empty IDs")
        return list(dict.fromkeys(values))


class FunctionCasesBatchDeleteResponse(BaseModel):
    deleted_ids: list[str]
    deleted_count: int
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CasePushCandidate(BaseModel):
    id: int
    title: str


class CasePushPreviewItem(BaseModel):
    case_id: str
    title: str
    mapped_remote_case_id: int | None = None
    operation: FunctionCaseZentaoImportItemResponse | None = None
    candidates: list[CasePushCandidate] = Field(default_factory=list)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CasePushPreview(BaseModel):
    can_confirm_not_applied: bool = False
    restore_required: bool = False
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    items: list[CasePushPreviewItem]


class CasePushReconcileRequest(BaseModel):
    resolution: Literal["confirm", "not_applied"] = "confirm"
    remote_case_id: int | None = Field(default=None, gt=0, le=2_147_483_647)
    reason: str = Field(default="", max_length=1000)
    confirmed_not_applied: bool = False
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
