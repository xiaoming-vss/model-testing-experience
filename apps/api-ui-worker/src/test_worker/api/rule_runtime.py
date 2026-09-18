"""Extract and assert runtime for API case results."""

from __future__ import annotations

import json
from typing import Any

from .template_runtime import render_template


def run_extract_rules(
    rules: list[dict[str, Any]],
    response: dict[str, Any],
    runtime_vars: dict[str, str],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for rule in sorted((r for r in rules if r.get("enabled", True)), key=lambda r: r.get("orderNo", 0)):
        value = ""
        error_message = ""
        used_default = False
        success = True
        try:
            extracted = _read_source(response, rule.get("source", ""), rule.get("sourceExpr", ""))
            if extracted is None or extracted == "":
                default_value = rule.get("defaultValue", "")
                if default_value:
                    extracted = render_template(default_value, runtime_vars)
                    used_default = True
                else:
                    raise ValueError("extracted value is empty")
            value = _stringify(extracted)
            runtime_vars[str(rule.get("varKey", ""))] = value
        except Exception as exc:
            success = False
            error_message = str(exc)

        results.append({
            "extractRuleId": rule.get("extractRuleId", ""),
            "name": rule.get("name", ""),
            "varKey": rule.get("varKey", ""),
            "success": success,
            "usedDefault": used_default,
            "value": value,
            "errorMessage": error_message,
        })
    return results


def run_assert_rules(
    rules: list[dict[str, Any]],
    response: dict[str, Any],
    runtime_vars: dict[str, str],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for rule in sorted((r for r in rules if r.get("enabled", True)), key=lambda r: r.get("orderNo", 0)):
        expected = render_template(rule.get("expectedValue", ""), runtime_vars)
        actual = ""
        success = False
        error_message = ""
        try:
            actual_value = _read_source(response, rule.get("assertSource", ""), rule.get("targetExpr", ""))
            actual = _stringify(actual_value)
            success = _compare(actual, expected, rule.get("comparator", "eq"))
            if not success:
                error_message = f"expected {expected}, got {actual}"
        except Exception as exc:
            error_message = str(exc)

        results.append({
            "assertRuleId": rule.get("assertRuleId", ""),
            "name": rule.get("name", ""),
            "success": success,
            "assertSource": rule.get("assertSource", ""),
            "targetExpr": rule.get("targetExpr", ""),
            "comparator": rule.get("comparator", ""),
            "expectedValue": expected,
            "actualValue": actual,
            "errorMessage": error_message,
        })
    return results


def _read_source(response: dict[str, Any], source: str, expr: str) -> Any:
    headers = _parse_json_dict(response.get("headersJson", "{}"))
    body = response.get("body", "")
    normalized = source or "body_jsonpath"
    if normalized == "status_code":
        return response.get("statusCode", 0)
    if normalized == "header":
        return _read_header(headers, expr)
    if normalized == "body_text":
        return body
    if normalized == "body_jsonpath":
        return _read_json_path(json.loads(body or "{}"), expr or "$")
    raise ValueError(f"unsupported source: {source}")


def _read_header(headers: dict[str, Any], name: str) -> Any:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return ""


def _read_json_path(value: Any, path: str) -> Any:
    if path in ("", "$"):
        return value
    if not path.startswith("$."):
        raise ValueError(f"unsupported jsonpath: {path}")
    current = value
    for token in path[2:].split("."):
        if isinstance(current, dict):
            current = current.get(token)
        elif isinstance(current, list) and token.isdigit():
            current = current[int(token)]
        else:
            return None
    return current


def _compare(actual: str, expected: str, comparator: str) -> bool:
    cmp = comparator or "eq"
    if cmp == "eq":
        return actual == expected
    if cmp == "neq":
        return actual != expected
    if cmp == "contains":
        return expected in actual
    if cmp == "not_contains":
        return expected not in actual
    if cmp == "empty":
        return actual == ""
    if cmp == "not_empty":
        return actual != ""
    if cmp in ("gt", "gte", "lt", "lte"):
        actual_number = float(actual)
        expected_number = float(expected)
        if cmp == "gt":
            return actual_number > expected_number
        if cmp == "gte":
            return actual_number >= expected_number
        if cmp == "lt":
            return actual_number < expected_number
        return actual_number <= expected_number
    raise ValueError(f"unsupported comparator: {comparator}")


def _parse_json_dict(raw: str) -> dict[str, Any]:
    parsed = json.loads(raw or "{}")
    return parsed if isinstance(parsed, dict) else {}


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
