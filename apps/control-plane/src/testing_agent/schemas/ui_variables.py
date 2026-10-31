from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ResolveUiRunVariablesRequest(BaseModel):
    task_id: str = Field()
    worker_id: str = Field()
    names: list[str] = Field(default_factory=list)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ResolveUiRunVariablesResponse(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    secret_names: list[str] = Field(default_factory=list)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WriteUiRunVariableItem(BaseModel):
    name: str = Field()
    value: str = Field(default="")
    order_no: int | None = Field(default=None)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WriteUiRunVariablesRequest(BaseModel):
    task_id: str = Field()
    worker_id: str = Field()
    items: list[WriteUiRunVariableItem] = Field(default_factory=list)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WriteUiRunVariableResult(BaseModel):
    name: str
    success: bool = True
    created: bool = False
    previous_value: str | None = Field(default=None)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WriteUiRunVariablesResponse(BaseModel):
    results: list[WriteUiRunVariableResult] = Field(default_factory=list)
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
