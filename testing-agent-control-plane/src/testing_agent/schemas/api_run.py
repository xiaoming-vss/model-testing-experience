from __future__ import annotations

# ruff: noqa: F401
import json
from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_serializer
from pydantic.alias_generators import to_camel


def json_text(value: Any, default: str = "{}") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value or default
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class RunApiCaseRequest(BaseModel):
    environment_id: str = Field()
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class RunApiCollectionRequest(RunApiCaseRequest):
    pass
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiCaseRunResponse(BaseModel):
    run_id: str = Field()
    case_id: str = Field()
    collection_id: str = Field()
    collection_run_id: str | None = Field(default=None)
    environment_id: str = Field()
    status: str
    success: bool = False
    error_message: str = Field()
    duration_ms: int = Field()
    request: Any | None = Field(
        default=None,
        validation_alias=AliasChoices("request", "request_snapshot_json"),
        serialization_alias="request",
    )
    response: Any | None = Field(
        default=None,
        validation_alias=AliasChoices("response", "response_snapshot_json"),
        serialization_alias="response",
    )
    runtime_vars_json: Any | None = Field(
        default=None,
        validation_alias=AliasChoices("runtimeVarsJson", "runtime_vars_json"),
        serialization_alias="runtimeVarsJson",
    )
    extract_results: list[Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("extractResults", "extract_results_json"),
        serialization_alias="extractResults",
    )
    assert_results: list[Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("assertResults", "assert_results_json"),
        serialization_alias="assertResults",
    )
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)

    @field_serializer("runtime_vars_json")
    def serialize_runtime_vars_json(self, value: Any) -> str:
        return json_text(value)


class ApiCollectionRunResponse(BaseModel):
    collection_run_id: str = Field()
    collection_id: str = Field()
    requirement_id: str = Field()
    sprint_id: str = Field()
    project_id: str = Field()
    environment_id: str = Field()
    trigger_user_id: str = Field()
    trigger_type: str = Field()
    status: str
    total_count: int = Field()
    success_count: int = Field()
    failed_count: int = Field()
    error_count: int = Field()
    skipped_count: int = Field()
    runtime_vars_json: Any | None = Field(
        default=None,
        validation_alias=AliasChoices("runtimeVarsJson", "runtime_vars_json"),
        serialization_alias="runtimeVarsJson",
    )
    error_message: str = Field()
    started_at: datetime | str | None = Field(default="")
    finished_at: datetime | str | None = Field(default="")
    duration_ms: int = Field()
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)

    @field_serializer("runtime_vars_json")
    def serialize_runtime_vars_json(self, value: Any) -> str:
        return json_text(value)


class ApiCollectionRunReportItem(BaseModel):
    item_id: str = Field()
    case_id: str = Field()
    case_run_id: str = Field()
    case_name: str = Field()
    order_no: int = Field()
    status: str
    continue_on_failure: bool = Field()
    error_message: str = Field()
    started_at: str = Field()
    finished_at: str = Field()
    duration_ms: int = Field()
    request: Any
    response: Any
    runtime_vars_json: str = Field()
    extract_results: list[Any] = Field()
    assert_results: list[Any] = Field()

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiCollectionRunReportResponse(ApiCollectionRunResponse):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    items: list[ApiCollectionRunReportItem]
