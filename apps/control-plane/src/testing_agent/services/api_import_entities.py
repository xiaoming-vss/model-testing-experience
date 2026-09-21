"""Normalize and construct API assets without committing a transaction."""

from typing import Any, Literal

from testing_agent.core.sid import new_id
from testing_agent.models.api_assert_rule import ApiAssertRule
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_extract_rule import ApiExtractRule
from testing_agent.services.api_import_payload import (
    bool_value,
    int_value,
    normalize_import_body_type,
    normalize_import_method,
    normalize_json_value,
    require_string_map,
)


def normalize_api_case(
    item: dict[str, Any], index: int, *, source: Literal["candidate", "file"] = "candidate"
) -> dict[str, Any]:
    body_type = normalize_import_body_type(item.get("bodyType"))
    body_json = normalize_json_value(item.get("bodyJson"))
    body_text = str(item.get("bodyText") or "")
    if body_type == "raw":
        body_json = None
    elif body_type == "none":
        body_json = None
        body_text = ""
    extract_rules = item.get("extractRules") or []
    assert_rules = item.get("assertRules") or []
    return {
        "name": (
            str(item.get("name") or f"API Case {index + 1}").strip()
            if source == "candidate"
            else str(item.get("name") or f"API Case {index + 1}")
        ),
        "description": str(item.get("description") or ""),
        "enabled": bool_value(item.get("enabled"), True),
        "orderNo": int_value(item.get("orderNo"), 0),
        "method": normalize_import_method(item.get("method")),
        "urlTemplate": str(item.get("urlTemplate") or ""),
        "headers": require_string_map(item.get("headers"), f"cases[{index}].headers"),
        "query": require_string_map(item.get("query"), f"cases[{index}].query"),
        "bodyType": body_type,
        "bodyJson": body_json,
        "bodyText": body_text,
        "timeoutMs": int_value(item.get("timeoutMs"), 5000),
        "continueOnFailure": bool_value(item.get("continueOnFailure"), False),
        "extractRules": [
            {
                "name": str(rule.get("name") or f"Extract Rule {rule_index + 1}"),
                "enabled": bool_value(rule.get("enabled"), True),
                "orderNo": (
                    int_value(rule.get("orderNo"), rule_index)
                    if source == "candidate"
                    else int(rule.get("orderNo", rule_index))
                ),
                "source": str(rule.get("source") or ""),
                "sourceExpr": str(rule.get("sourceExpr") or ""),
                "varKey": (
                    str(rule.get("varKey") or "").strip()
                    if source == "candidate"
                    else str(rule.get("varKey") or "")
                ),
                "defaultValue": str(rule.get("defaultValue") or ""),
            }
            for rule_index, rule in enumerate(extract_rules)
            if isinstance(rule, dict)
        ],
        "assertRules": [
            {
                "name": str(rule.get("name") or f"Assert Rule {rule_index + 1}"),
                "enabled": bool_value(rule.get("enabled"), True),
                "orderNo": (
                    int_value(rule.get("orderNo"), rule_index)
                    if source == "candidate"
                    else int(rule.get("orderNo", rule_index))
                ),
                "assertSource": str(rule.get("assertSource") or ""),
                "targetExpr": str(rule.get("targetExpr") or ""),
                "comparator": str(rule.get("comparator") or ""),
                "expectedValue": str(rule.get("expectedValue") or ""),
            }
            for rule_index, rule in enumerate(assert_rules)
            if isinstance(rule, dict)
        ],
    }


def apply_api_case(case: ApiCase, item: dict[str, Any]) -> None:
    case.name = item["name"]
    case.description = item["description"]
    case.enabled = item["enabled"]
    case.order_no = item["orderNo"]
    case.method = item["method"]
    case.url_template = item["urlTemplate"]
    case.headers_json = item["headers"]
    case.query_json = item["query"]
    case.body_type = item["bodyType"]
    case.body_json = item["bodyJson"]
    case.body_text = item["bodyText"]
    case.timeout_ms = item["timeoutMs"]
    case.continue_on_failure = item["continueOnFailure"]


def add_api_rules(repository, case_id: str, item: dict[str, Any]) -> None:
    for rule in item["extractRules"]:
        repository.add(
            ApiExtractRule(
                extract_rule_id=new_id(),
                case_id=case_id,
                name=rule["name"],
                enabled=rule["enabled"],
                order_no=rule["orderNo"],
                source=rule["source"],
                source_expr=rule["sourceExpr"],
                var_key=rule["varKey"],
                default_value=rule["defaultValue"],
            )
        )
    for rule in item["assertRules"]:
        repository.add(
            ApiAssertRule(
                assert_rule_id=new_id(),
                case_id=case_id,
                name=rule["name"],
                enabled=rule["enabled"],
                order_no=rule["orderNo"],
                assert_source=rule["assertSource"],
                target_expr=rule["targetExpr"],
                comparator=rule["comparator"],
                expected_value=rule["expectedValue"],
            )
        )
