"""Stage-two shape contract and actionable repair feedback."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from .artifacts import validate_design


class Contract(BaseModel):
    # Existing v2 artifacts permit descriptive extension fields; retain compatibility.
    model_config = ConfigDict(strict=True, extra="allow")


class Action(Contract):
    actionId: str = Field(min_length=1)
    sourceQuote: str = Field(min_length=1)
    action: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    target: str
    value: JsonValue
    status: Literal["included", "excluded"]
    reason: str = ""


class Expectation(Contract):
    expectationId: str = Field(min_length=1)
    sourceQuote: str = Field(min_length=1)
    assertion: str = Field(min_length=1)
    target: str
    value: JsonValue
    status: Literal["included", "excluded", "bookkeeping"]
    reason: str = ""


class Step(Contract):
    sourceStepNo: int = Field(ge=1)
    sourceAction: str
    actions: list[Action]
    expectations: list[Expectation]


class Case(Contract):
    caseId: str = Field(min_length=1)
    name: str = Field(min_length=1)
    sourceTitle: str
    preconditions: list[str]
    goal: str = Field(min_length=1)
    coreExpectationIds: list[str] = Field(min_length=1)
    steps: list[Step]
    coverage: Literal["full", "partial", "excluded"]
    limitations: list[str]


class Capabilities(Contract):
    operations: list[str]
    assertions: list[str]


class Design(Contract):
    schemaVersion: Literal["ui_test_scenarios/2.0"]
    capabilities: Capabilities
    cases: list[Case] = Field(min_length=1)


def strict_json(raw: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"JSON 重复字段: {key}")
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise ValueError(f"JSON 不允许非有限数值: {value}")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def design_instruction() -> str:
    return (
        "\n第二阶段返回的完整 JSON 对象必须符合以下 JSON Schema：\n"
        + json.dumps(Design.model_json_schema(), ensure_ascii=False)
        + "\n必须保留全部 functionalCases，逐条逐步覆盖原始操作和预期。"
        "sourceQuote 必须从相应原文连续逐字复制，不润色、不增删字；拆分后不得遗漏或重复覆盖。"
        "缺少元素、定位或数据不能作为排除理由。只排除平台不支持的操作或断言。"
        "不得修改已审核 surface 或原始用例来通过校验。"
    )


def validate_design_output(value: Any, cases: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        Design.model_validate(value)
    except ValidationError as exc:
        issues = [
            {
                "path": "$"
                + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in e["loc"]),
                "code": e["type"],
                "expected": e["msg"],
                "actual": e.get("input"),
            }
            for e in exc.errors(include_url=False, include_context=False)[:20]
        ]
        raise ValueError(json.dumps(issues, ensure_ascii=False, default=str)) from exc
    originals = {case["caseId"]: case for case in cases}
    issues = []
    for i, case in enumerate(value["cases"]):
        original = originals.get(case["caseId"])
        if original is None:
            continue
        base = f"$.cases[{i}]"
        for field, expected in (
            ("sourceTitle", original["title"]),
            ("preconditions", original["content"].get("preconditions", [])),
        ):
            if case[field] != expected:
                issues.append(
                    dict(
                        path=f"{base}.{field}",
                        caseId=case["caseId"],
                        code="source_changed",
                        expected=expected,
                        actual=case[field],
                    )
                )
        for j, (step, source) in enumerate(zip(case["steps"], original["content"]["steps"])):
            for group, source_field in (("actions", "action"), ("expectations", "expected")):
                for k, item in enumerate(step[group]):
                    if item["sourceQuote"] not in source[source_field]:
                        issues.append(
                            dict(
                                path=f"{base}.steps[{j}].{group}[{k}].sourceQuote",
                                caseId=case["caseId"],
                                sourceStepNo=j + 1,
                                code="source_quote_changed",
                                expected=source[source_field],
                                actual=item["sourceQuote"],
                                rule="从 expected 原文逐字复制连续片段；保留其他片段，完整且不重复覆盖",
                            )
                        )
    if issues:
        raise ValueError(json.dumps(issues[:20], ensure_ascii=False))
    try:
        return validate_design(value, cases)
    except ValueError as exc:
        raise ValueError(
            json.dumps(
                [
                    dict(
                        path="$.cases",
                        code="business_contract",
                        expected=message,
                        actual="参见上一次输出中对应 caseId/step/操作或预期 ID 的当前内容",
                    )
                    for message in str(exc).split("; ")[:20]
                ],
                ensure_ascii=False,
            )
        ) from exc
