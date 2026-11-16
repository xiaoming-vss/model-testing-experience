"""API assertion comparator runtime: exists and regex behavior."""

from __future__ import annotations

from typing import Any

from test_worker.api.rule_runtime import run_assert_rules


def _response() -> dict[str, Any]:
    return {
        "statusCode": 200,
        "headersJson": '{"X-Trace":"trace-1"}',
        "body": '{"data":{"accessToken":"token-1","code":0,"name":""}}',
    }


def _rule(**overrides: Any) -> dict[str, Any]:
    rule: dict[str, Any] = {
        "assertRuleId": "assert-1",
        "name": "返回访问令牌存在",
        "enabled": True,
        "orderNo": 1,
        "assertSource": "body_jsonpath",
        "targetExpr": "$.data.accessToken",
        "comparator": "exists",
        "expectedValue": "",
    }
    rule.update(overrides)
    return rule


def test_exists_accepts_present_values_including_zero():
    results = run_assert_rules(
        [
            _rule(),
            _rule(assertRuleId="assert-2", targetExpr="$.data.code"),
        ],
        _response(),
        {},
    )

    assert [result["success"] for result in results] == [True, True]


def test_exists_rejects_missing_and_empty_values():
    results = run_assert_rules(
        [
            _rule(targetExpr="$.data.missing"),
            _rule(assertRuleId="assert-2", targetExpr="$.data.name"),
            _rule(
                assertRuleId="assert-3", assertSource="header", targetExpr="X-Missing"
            ),
        ],
        _response(),
        {},
    )

    assert [result["success"] for result in results] == [False, False, False]


def test_regex_matches_actual_value():
    results = run_assert_rules(
        [
            _rule(comparator="regex", expectedValue=r"^token-\d+$"),
            _rule(
                assertRuleId="assert-2",
                comparator="regex",
                expectedValue=r"^missing$",
            ),
        ],
        _response(),
        {},
    )

    assert [result["success"] for result in results] == [True, False]


def test_invalid_regex_reports_error():
    result = run_assert_rules(
        [_rule(comparator="regex", expectedValue="[")],
        _response(),
        {},
    )[0]

    assert result["success"] is False
    assert result["errorMessage"] == "invalid regex: ["
