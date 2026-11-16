"""生成 YAML 与 API 用例设计的严格对齐校验。"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

import yaml

from testing_agent_ai_worker.tasks.api_case_generate.contracts import Cases, parse_yaml
from testing_agent_ai_worker.tasks.api_case_generate.design_contract import (
    pointer_tokens,
    resolve_pointer,
)


class GenerationAlignmentError(ValueError):
    """生成的 YAML 与已审核设计不一致。"""


def _fail(path: str, message: str) -> None:
    raise GenerationAlignmentError(f"{path}: {message}")


def flatten_design(design: dict[str, Any]) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for name, interface in design["interfaces"].items():
        for case in interface["cases"]:
            rows.append((name, interface, case))
    return rows


def _expected_url(interface: dict[str, Any], case: dict[str, Any]) -> str:
    path = interface["path"]
    for op in case.get("patch", {}).get("path_params", []):
        tokens = pointer_tokens(op.get("path"), "patch.path_params.path")
        if len(tokens) != 1:
            _fail("patch.path_params", "路径参数补丁必须指向单个参数")
        if op["op"] in {"add", "replace"}:
            path = path.replace("{" + tokens[0] + "}", str(op.get("value")))
    return path


def _status_pairs(status_class: str) -> set[tuple[str, str]]:
    return (
        {("gte", "200"), ("lt", "300")}
        if status_class == "2xx"
        else {("gte", "400"), ("lt", "500")}
    )


def _strict_equal(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        return actual is expected
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return (
            isinstance(actual, (int, float)) and not isinstance(actual, bool) and actual == expected
        )
    if isinstance(expected, str):
        return isinstance(actual, str) and actual == expected
    if expected is None:
        return actual is None
    return actual == expected


def _header_equal(actual: Any, expected: Any) -> bool:
    return actual is not None and str(actual) == str(expected)


def _section_actual(case: Any, section: str) -> Any:
    if section == "headers":
        return case.headers or {}
    if section == "query":
        return case.query or {}
    if section in {"json", "data"}:
        return case.bodyJson
    return None


def _patch_expected_keys(
    interface: dict[str, Any],
    section: str,
    design_case: dict[str, Any],
) -> set[str] | None:
    """按设计补丁推导分区应包含的顶层字段；非对象分区返回 None。"""

    base = interface.get(section)
    if not isinstance(base, dict):
        return None
    expected = set(base)
    for op in design_case.get("patch", {}).get(section, []):
        tokens = pointer_tokens(op.get("path"), "patch")
        if len(tokens) != 1:
            continue
        if op["op"] == "remove":
            expected.discard(tokens[0])
        else:
            expected.add(tokens[0])
    return expected


_REQUIRED_MARKER = re.compile(r"(?<![非不])必传")


def _required_keys(interface: dict[str, Any], section: str) -> set[str]:
    base = interface.get(section)
    if not isinstance(base, dict):
        return set()
    return {
        key
        for key, value in base.items()
        if isinstance(value, str) and _REQUIRED_MARKER.search(value)
    }


def _compare_keys(
    actual: Any,
    expected: set[str],
    required: set[str],
    *,
    label: str,
    path: str,
) -> None:
    if not isinstance(actual, dict):
        _fail(path, f"YAML 的 {label} 必须是对象")
    missing = sorted((required & expected) - set(actual))
    extra = sorted(set(actual) - expected)
    if missing:
        _fail(path, f"YAML 的 {label} 缺少必传字段：{', '.join(missing)}")
    if extra:
        _fail(path, f"YAML 的 {label} 包含提取基线之外字段：{', '.join(extra)}")


def _check_baseline_request(
    case: Any,
    interface: dict[str, Any],
    design_case: dict[str, Any],
    path: str,
) -> None:
    """校验生成请求覆盖且仅覆盖提取基线加上设计补丁后的字段集合。"""

    for section, actual in (("headers", case.headers or {}), ("query", case.query or {})):
        expected = _patch_expected_keys(interface, section, design_case)
        if expected is None:
            if actual:
                _fail(path, f"YAML 包含提取基线之外的 {section} 数据")
            continue
        _compare_keys(
            actual,
            expected,
            _required_keys(interface, section),
            label=section,
            path=path,
        )
    body_section = "json" if "json" in interface else "data" if "data" in interface else None
    patch_sections = set(design_case.get("patch", {}))
    if body_section is None:
        if patch_sections & {"json", "data"}:
            _fail(path, "设计补丁引用了提取基线不存在的请求体")
        if case.bodyType != "none" or case.bodyJson is not None or case.bodyText.strip():
            _fail(path, "提取基线没有请求体，YAML 必须使用 bodyType none 且不发送请求体")
        return
    expected_body_type = "json" if body_section == "json" else "form"
    if case.bodyType != expected_body_type:
        _fail(path, f"提取基线要求 bodyType 为 {expected_body_type}")
    base = interface.get(body_section)
    if isinstance(base, dict):
        expected = _patch_expected_keys(interface, body_section, design_case)
        assert expected is not None
        _compare_keys(
            case.bodyJson,
            expected,
            _required_keys(interface, body_section),
            label=body_section,
            path=path,
        )
    elif isinstance(base, list):
        if not isinstance(case.bodyJson, list):
            _fail(path, f"YAML 的 {body_section} 请求体必须是数组")


def _expected_list_length(base: list[Any], ops: list[dict[str, Any]]) -> int:
    length = len(base)
    for op in ops:
        tokens = pointer_tokens(op.get("path"), "patch")
        if len(tokens) != 1:
            continue
        if op["op"] == "remove":
            length -= 1
        elif op["op"] == "add":
            length += 1
    return length


def _check_patch_effects(
    case: Any,
    interface: dict[str, Any],
    design_case: dict[str, Any],
    path: str,
) -> None:
    for section, ops in design_case.get("patch", {}).items():
        if section == "path_params":
            continue
        actual = _section_actual(case, section)
        compare = _header_equal if section == "headers" else _strict_equal
        if not isinstance(actual, (dict, list)):
            _fail(path, f"YAML 缺少 {section} 请求数据，无法落实补丁")
        base = interface.get(section)
        top_level_list = isinstance(base, list)
        if top_level_list:
            if not isinstance(actual, list):
                _fail(path, f"YAML 的 {section} 必须是数组")
            expected_length = _expected_list_length(base, ops)
            if not isinstance(actual, list) or len(actual) != expected_length:
                _fail(
                    path,
                    f"YAML 的 {section} 数组长度必须为 {expected_length}，"
                    f"实际为 {len(actual) if isinstance(actual, list) else '非数组'}",
                )
        for index, op in enumerate(ops):
            tokens = pointer_tokens(op.get("path"), f"{path}.patch.{section}[{index}]")
            last = tokens[-1]
            if top_level_list:
                # 顶层数组的删除/插入会移动索引，长度已在上方校验；单值补丁再核对元素值。
                if len(ops) == 1 and op["op"] != "remove" and last != "-":
                    if not last.isdigit() or int(last) >= len(actual):
                        _fail(path, f"补丁目标 {section}{op['path']} 的数组索引越界")
                    if not compare(actual[int(last)], op.get("value")):
                        _fail(path, f"补丁目标 {section}{op['path']} 的值与设计不一致")
                continue
            found, parent = resolve_pointer(actual, tokens[:-1])
            if op["op"] == "remove":
                if not found:
                    continue
                present = (
                    last in parent
                    if isinstance(parent, dict)
                    else isinstance(parent, list) and last.isdigit() and int(last) < len(parent)
                )
                if present:
                    _fail(path, f"补丁要求删除 {section}{op['path']}，YAML 中仍然存在")
                continue
            if not found:
                _fail(path, f"补丁目标 {section}{op['path']} 的父容器在 YAML 中不存在")
            if isinstance(parent, dict):
                if last not in parent:
                    _fail(path, f"补丁目标 {section}{op['path']} 在 YAML 中不存在")
                actual_value = parent[last]
            elif isinstance(parent, list):
                if last == "-" or not last.isdigit() or int(last) >= len(parent):
                    _fail(path, f"补丁目标 {section}{op['path']} 的数组索引越界")
                actual_value = parent[int(last)]
            else:
                _fail(path, f"补丁目标 {section}{op['path']} 不是对象或数组")
            if not compare(actual_value, op.get("value")):
                _fail(path, f"补丁目标 {section}{op['path']} 的值与设计不一致")


def _check_assertions(
    case: Any,
    design_case: dict[str, Any],
    path: str,
) -> None:
    if not case.enabled:
        _fail(path, "生成用例必须启用")
    if any(not rule.enabled for rule in case.assertRules):
        _fail(path, "生成断言必须启用")
    status_class = design_case["expected"]["statusClass"]
    status_rules = [rule for rule in case.assertRules if rule.assertSource == "status_code"]
    business_rules = [rule for rule in case.assertRules if rule.assertSource != "status_code"]
    actual_status = {(rule.comparator, rule.expectedValue) for rule in status_rules}
    if len(status_rules) != 2 or actual_status != _status_pairs(status_class):
        _fail(path, f"状态断言必须恰好落实 {status_class} 的状态码区间")
    expected = Counter(
        (
            item["assertSource"],
            item["targetExpr"],
            item["comparator"],
            item["expectedValue"],
        )
        for item in design_case["expected"]["assertions"]
    )
    actual = Counter(
        (rule.assertSource, rule.targetExpr, rule.comparator, rule.expectedValue)
        for rule in business_rules
    )
    if actual != expected:
        missing = len(list((expected - actual).elements()))
        extra = len(list((actual - expected).elements()))
        _fail(path, f"业务断言与设计不一致（缺少 {missing} 条，多出 {extra} 条）")


def _check_body_type(case: Any, design_case: dict[str, Any], path: str) -> None:
    patch = design_case.get("patch", {})
    if "json" in patch and case.bodyType != "json":
        _fail(path, "json 补丁要求 bodyType 为 json")
    if "data" in patch and case.bodyType != "form":
        _fail(path, "data 补丁要求 bodyType 为 form")


def validate_generated_cases_object(
    parsed: Any,
    extraction: dict[str, Any],
    design: dict[str, Any],
    *,
    start_order_no: int = 1,
) -> Cases:
    """校验 YAML 对象与设计逐条对齐；支持单批的全局序号偏移。"""

    cases = Cases.model_validate(parsed)
    rows = flatten_design(design)
    if len(cases.cases) != len(rows):
        _fail(
            "cases",
            f"用例数量必须与设计一致：设计 {len(rows)} 条，YAML {len(cases.cases)} 条",
        )
    for index, (case, (name, interface, design_case)) in enumerate(
        zip(cases.cases, rows, strict=True)
    ):
        path = f"cases[{index}]"
        baseline = extraction.get(name)
        if not isinstance(baseline, dict):
            _fail(path, f"提取产物缺少接口 {name} 的基线")
        assert isinstance(baseline, dict)
        expected_order = start_order_no + index
        if case.orderNo != expected_order:
            _fail(path, f"orderNo 必须是全局序号 {expected_order}")
        if case.name != design_case["title"]:
            _fail(path, f"name 必须等于设计 title：{design_case['title']}")
        if case.description != design_case["intent"]:
            _fail(path, "description 必须等于设计 intent")
        if case.extractRules:
            _fail(path, "不允许生成设计之外的提取规则")
        if case.method != interface["method"]:
            _fail(path, f"method 必须与接口 {name} 的提取基线一致")
        expected_url = _expected_url(interface, design_case)
        if case.urlTemplate != expected_url:
            _fail(path, f"urlTemplate 必须是 {expected_url}")
        _check_body_type(case, design_case, path)
        _check_baseline_request(case, baseline, design_case, path)
        _check_patch_effects(case, baseline, design_case, path)
        _check_assertions(case, design_case, path)
    return cases


def validate_generated_cases_json(
    raw: str,
    extraction: dict[str, Any],
    design: dict[str, Any],
    *,
    start_order_no: int = 1,
) -> Cases:
    return validate_generated_cases_object(
        parse_yaml(raw), extraction, design, start_order_no=start_order_no
    )


def dump_case_dicts(cases: list[dict[str, Any]]) -> str:
    return yaml.safe_dump(
        {"cases": cases},
        allow_unicode=True,
        sort_keys=False,
    )


def dump_cases(cases: list[Any]) -> str:
    return dump_case_dicts([case.model_dump(mode="json") for case in cases])
