from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic.alias_generators import to_camel

from testing_agent.domain.ui_variable_template import (
    TOKEN_PATTERN,
    parse_tokens,
    validate_locator_tokens,
)
from testing_agent.domain.variable_names import validate_variable_name
from testing_agent.schemas.common import StrictRequest

GroupKind = Literal["common", "page"]
LocatorType = Literal["css", "xpath", "text", "placeholder", "label", "test_id", "role"]
VerificationStatus = Literal["pending", "verified"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Scope = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Route = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)]
Locator = Annotated[str, StringConstraints(min_length=1, max_length=4096)]
GroupId = Annotated[str, StringConstraints(min_length=1, max_length=64)]


class UiElementRequest(StrictRequest):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UiElementGroupCreate(UiElementRequest):
    name: Name
    route_template: Route

    @model_validator(mode="after")
    def validate_route(self) -> UiElementGroupCreate:
        route = self.route_template
        if (
            not route.startswith("/")
            or route.startswith("//")
            or any(character in "?#\\" or character.isspace() for character in route)
            or not route.isprintable()
        ):
            raise ValueError("请输入应用内路由模板，例如 /orders/:id")
        return self


class UiElementParameter(UiElementRequest):
    name: Name
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] = ""


class UiElementCreate(UiElementRequest):
    group_id: GroupId | None = None
    name: Name
    scope: Scope
    locator_type: LocatorType
    locator_value: Locator
    parameters: list[UiElementParameter] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def validate_template(self) -> UiElementCreate:
        value = self.locator_value
        if not value.strip():
            raise ValueError("定位值不能为空")
        remainder = TOKEN_PATTERN.sub("", value)
        if "{{" in remainder or "}}" in remainder:
            raise ValueError("定位模板包含未闭合的参数")
        matches = list(TOKEN_PATTERN.finditer(value))
        tokens = parse_tokens(value)
        if len(matches) != len(tokens):
            raise ValueError("定位模板仅接受命名参数")
        validate_locator_tokens(value, self.locator_type)
        names = [validate_variable_name(parameter.name) for parameter in self.parameters]
        if len(set(names)) != len(names) or set(names) != {token.name for token in tokens}:
            raise ValueError("参数定义必须与定位模板中的占位符一一对应")
        return self


class UiElementUpdate(UiElementRequest):
    version: int = Field(ge=1)
    group_id: GroupId | None = None
    name: Name | None = None
    scope: Scope | None = None
    locator_type: LocatorType | None = None
    locator_value: Locator | None = None
    parameters: list[UiElementParameter] | None = Field(default=None, max_length=64)


class UiElementListFilters(BaseModel):
    group_id: GroupId | None = None
    keyword: str = Field(default="", max_length=120)
    verification_status: VerificationStatus | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class UiElementGroupView(BaseModel):
    group_id: str
    kind: GroupKind
    name: str
    route_template: str
    element_count: int

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UiElementSummary(BaseModel):
    element_id: str
    group_id: str
    name: str
    scope: str
    locator_type: LocatorType
    parameterized: bool
    verification_status: VerificationStatus
    version: int

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class UiElementDetail(UiElementSummary):
    locator_value: str
    parameters: list[UiElementParameter] = Field(validation_alias="parameters_json")
    updated_at: datetime
