"""API skill outputs and the platform's candidate import contract."""

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from testing_agent_ai_worker_pi.tasks.output_repair import parse_yaml

METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE"}


def unique_pairs(pairs: list[tuple[Any, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"重复字段: {key}")
        result[key] = value
    return result


def invalid_constant(value: str) -> None:
    raise ValueError(f"非法 JSON 数值: {value}")


def validate_extraction(raw: str) -> None:
    data = json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=invalid_constant)
    if not isinstance(data, dict) or not data:
        raise ValueError("接口配置必须是以 snake_case 接口名称为键的非空 JSON 对象")
    for name, endpoint in data.items():
        if not re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*", name):
            raise ValueError("接口名称必须是 snake_case")
        if not isinstance(endpoint, dict):
            raise ValueError(f"{name} 必须是接口配置对象")
        allowed = {"path", "method", "headers", "path_params", "query", "json", "data", "response"}
        if set(endpoint) - allowed:
            raise ValueError(f"{name} 含不支持字段")
        if not isinstance(endpoint.get("path"), str) or not endpoint["path"].startswith("/"):
            raise ValueError(f"{name}.path 必须是以 / 开头的接口路径")
        if not isinstance(endpoint.get("method"), str) or endpoint["method"] not in METHODS:
            raise ValueError(f"{name}.method 必须是有效 HTTP 方法")
        for section in ("headers", "path_params", "query"):
            if section in endpoint and not isinstance(endpoint[section], dict):
                raise ValueError(f"{name}.{section} 必须是对象")
        if "json" in endpoint and "data" in endpoint:
            raise ValueError(f"{name} 不可同时包含 json 和 data 请求体")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Rule(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    enabled: bool = True
    orderNo: int = Field(default=0, ge=0)


class ExtractRule(Rule):
    source: Literal["header", "body_jsonpath", "body_text", "status_code"]
    sourceExpr: str = Field(default="", max_length=512)
    varKey: str = Field(min_length=1, max_length=100)
    defaultValue: str = ""


class AssertRule(Rule):
    assertSource: Literal["header", "body_jsonpath", "body_text", "status_code"]
    targetExpr: str = Field(default="", max_length=512)
    comparator: Literal[
        "eq", "neq", "contains", "not_contains", "gt", "gte", "lt", "lte", "exists", "regex"
    ]
    expectedValue: str = ""


class ApiCase(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=512)
    enabled: bool = True
    orderNo: int = Field(ge=0)
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"]
    urlTemplate: str = Field(min_length=1, max_length=1024)
    headers: dict[str, Any] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    bodyType: Literal["json", "form", "raw", "none"] = "json"
    bodyJson: dict[str, Any] | None = None
    bodyText: str = ""
    timeoutMs: int = Field(default=5000, ge=0)
    continueOnFailure: bool = False
    extractRules: list[ExtractRule] = Field(default_factory=list)
    assertRules: list[AssertRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_body_and_rules(self) -> "ApiCase":
        if not self.name.strip() or not self.urlTemplate.strip():
            raise ValueError("name/urlTemplate 不得为空白")
        if self.bodyType in {"raw", "none"} and self.bodyJson is not None:
            raise ValueError("raw/none 请求体不能包含 bodyJson")
        if self.bodyType == "none" and self.bodyText.strip():
            raise ValueError("none 请求体不能包含 bodyText")
        keys = [rule.varKey.strip() for rule in self.extractRules]
        if any(not key for key in keys) or len(keys) != len(set(keys)):
            raise ValueError("同用例的提取 varKey 必须非空且唯一")
        if any(not rule.name.strip() for rule in [*self.extractRules, *self.assertRules]):
            raise ValueError("规则名称不得为空白")
        names = [rule.name.strip() for rule in self.assertRules]
        if len(names) != len(set(names)):
            raise ValueError("同用例的断言规则名称重复")
        return self


class Cases(StrictModel):
    cases: list[ApiCase] = Field(min_length=1)

    @model_validator(mode="after")
    def check_names_and_order(self) -> "Cases":
        names = [case.name.strip().casefold() for case in self.cases]
        if len(names) != len(set(names)):
            raise ValueError("用例名称重复")
        order = [case.orderNo for case in self.cases]
        if order != sorted(order):
            raise ValueError("cases 必须按 orderNo 升序排列")
        return self


def validate_cases(raw: str) -> None:
    Cases.model_validate(parse_yaml(raw))
