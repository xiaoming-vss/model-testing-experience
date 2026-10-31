"""Static pre-run check that every referenced variable can be resolved."""

from __future__ import annotations

from typing import Any

from testing_agent.domain.ui_variable_template import parse_tokens

BASE_URL_NAME = "baseUrl"


def missing_variables(
    cases: list[dict[str, Any]],
    available: set[str],
    *,
    base_url: str,
) -> list[dict[str, Any]]:
    """Return every unresolved reference, ordered by case and step."""
    base_url_configured = bool(base_url.strip())
    missing: list[dict[str, Any]] = []
    for case in cases:
        # 每个用例从环境当前值重新起算：不推算前面用例的提取结果。
        known = set(available)
        case_id = str(case.get("caseId") or "")
        case_name = str(case.get("name") or "")
        for step in _ordered_steps(case):
            for field in ("locatorValue", "operationValue"):
                value = step.get(field)
                if not isinstance(value, str):
                    continue
                for token in parse_tokens(value):
                    if token.name == BASE_URL_NAME:
                        if not base_url_configured:
                            missing.append(
                                _entry(case_id, case_name, step, field, token.name, "builtin")
                            )
                        continue
                    if token.name not in known:
                        missing.append(
                            _entry(case_id, case_name, step, field, token.name, "environment")
                        )
            # 本步骤成功后变量才可用，因此登记发生在引用校验之后，且禁用步骤不会走到这里。
            known.update(save_to_names(step))
    return missing


def save_to_names(step: dict[str, Any]) -> list[str]:
    """Names declared by a step's post-action extraction rules."""
    raw = step.get("saveTo")
    if not isinstance(raw, list):
        return []
    return [
        str(item["name"]).strip()
        for item in raw
        if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].strip()
    ]


def _ordered_steps(case: dict[str, Any]) -> list[dict[str, Any]]:
    steps = [step for step in (case.get("stepsJson") or []) if isinstance(step, dict)]
    steps.sort(key=lambda step: step.get("orderNo") or 0)
    return [step for step in steps if step.get("enabled") is not False]


def _entry(
    case_id: str,
    case_name: str,
    step: dict[str, Any],
    field: str,
    name: str,
    kind: str,
) -> dict[str, Any]:
    reason = "环境未配置基础地址" if kind == "builtin" else "环境变量不存在"
    return {
        "caseId": case_id,
        "caseName": case_name,
        "orderNo": step.get("orderNo") or 0,
        "stepName": str(step.get("stepName") or ""),
        "field": field,
        "name": name,
        "kind": kind,
        "reason": reason,
    }
