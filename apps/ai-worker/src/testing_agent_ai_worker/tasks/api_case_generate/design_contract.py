"""API 用例设计产物契约与提取基线校验。

设计产物是提取产物与 YAML 生成之间的可审核中间层：每条用例必须引用提取基线中
存在的字段、类型或约束，并通过 JSON Patch 表达参数变异。本模块只做结构与业务
校验，不调用模型。
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from testing_agent_ai_worker.tasks.runtime_json import strict_json as loads_strict_json

DESIGN_SCHEMA_VERSION = "api_test_design/1.0"

SECTIONS = ("headers", "path_params", "query", "json", "data")
BODY_SECTIONS = ("json", "data")
CATEGORIES = {"positive", "negative", "boundary"}
PRIORITIES = {"P0", "P1", "P2"}
BASIS_KINDS = {"positive", "required", "constraint", "type"}
UNCOVERED_KINDS = {"required", "constraint", "type"}
UNCOVERED_REASONS = {"soft_cap", "low_value", "duplicate", "not_verifiable"}
STATUS_CLASSES = {"2xx", "4xx"}
ASSERT_SOURCES = {"header", "body_jsonpath", "body_text"}
COMPARATORS = {
    "eq",
    "neq",
    "contains",
    "not_contains",
    "gt",
    "gte",
    "lt",
    "lte",
    "exists",
    "regex",
}

_TYPE_PREFIX = re.compile(r"^(string|integer|number|boolean|object|array)\b", re.IGNORECASE)
_BOUNDARY_CONSTRAINT = re.compile(
    r"^(minimum|maximum|minLength|maxLength|min|max)\s*:\s*(-?\d+(?:\.\d+)?)$",
    re.IGNORECASE,
)
_ENUM_CONSTRAINT = re.compile(r"\benum\s*:\s*([^#)\s]+)", re.IGNORECASE)
_FORMAT_CONSTRAINT = re.compile(r"\bformat\s*:\s*([A-Za-z0-9_.-]+)", re.IGNORECASE)
_JSON_PATH = re.compile(r"^\$(?:\.[A-Za-z0-9_-]+|\[\d+\])*$")


class DesignValidationError(ValueError):
    """设计产物不符合契约或无法由提取基线支撑。"""


def strict_json(raw: str) -> Any:
    """解析严格 JSON；拒绝重复键、NaN 和 Infinity。"""

    if not isinstance(raw, str):
        raise DesignValidationError("设计产物必须是 JSON 文本")
    try:
        return loads_strict_json(
            raw,
            duplicate_message="重复字段",
            constant_message="非法 JSON 数值",
        )
    except (TypeError, ValueError) as exc:
        raise DesignValidationError(f"设计产物必须是合法 JSON：{exc}") from exc


def parse_design_json(raw: str) -> dict[str, Any]:
    data = strict_json(raw)
    if not isinstance(data, dict):
        raise DesignValidationError("设计产物顶层必须是 JSON 对象")
    return data


def _fail(path: str, message: str) -> None:
    raise DesignValidationError(f"{path}: {message}")


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(path, "必须是对象")
    return value


def _array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(path, "必须是数组")
    return value


def _text(value: Any, path: str, *, minimum: int = 1, maximum: int) -> str:
    if not isinstance(value, str):
        _fail(path, "必须是字符串")
    if not minimum <= len(value) <= maximum:
        _fail(path, f"长度必须在 {minimum}-{maximum} 之间")
    return value


def _pointer_tokens(pointer: Any, path: str) -> list[str]:
    if not isinstance(pointer, str) or not pointer.startswith("/") or pointer == "/":
        _fail(path, "必须是以 / 开头的相对 JSON Pointer")
    tokens = pointer[1:].split("/")
    for token in tokens:
        if re.search(r"~(?![01])", token):
            _fail(path, "JSON Pointer 转义非法")
    if any(not token for token in tokens):
        _fail(path, "JSON Pointer 不能包含空字段名")
    return [token.replace("~1", "/").replace("~0", "~") for token in tokens]


def _resolve(root: Any, tokens: list[str]) -> tuple[bool, Any]:
    current = root
    for token in tokens:
        if isinstance(current, dict):
            if token not in current:
                return False, None
            current = current[token]
        elif isinstance(current, list):
            if not token.isdigit():
                return False, None
            index = int(token)
            if index >= len(current):
                return False, None
            current = current[index]
        else:
            return False, None
    return True, current


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _type_matches(value: Any, declared: str) -> bool:
    actual = _json_type(value)
    declared = declared.lower()
    if declared == "number":
        return actual in {"integer", "number"}
    return actual == declared


def _declared_type(value: Any) -> str:
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        match = _TYPE_PREFIX.match(value.strip())
        return match.group(1).lower() if match else ""
    return ""


def _description(value: Any) -> str:
    if isinstance(value, str):
        return value
    return ""


_REQUIRED_MARKER = re.compile(r"(?<![非不])必传")


def _required(value: Any) -> bool:
    # 提取产物使用“必传/可选”或“[必传]”标记；“非必传”表示可选，不能按子串误判。
    return _REQUIRED_MARKER.search(_description(value)) is not None


def _normalized(text: str) -> str:
    return re.sub(r"\s+", "", text).casefold()


def _constraint_matches(value: Any, constraint: str) -> bool:
    description = _description(value)
    if not description:
        return False
    return constraint in description or _normalized(constraint) in _normalized(description)


def _enum_values(value: Any) -> list[str]:
    match = _ENUM_CONSTRAINT.search(_description(value))
    if match is None:
        return []
    return [item.strip() for item in match.group(1).split(",") if item.strip()]


def _format_value(value: Any) -> str:
    match = _FORMAT_CONSTRAINT.search(_description(value))
    return match.group(1) if match else ""


def _boundary(constraint: str) -> tuple[str, float] | None:
    match = _BOUNDARY_CONSTRAINT.match(constraint.strip())
    if match is None:
        return None
    return match.group(1).lower(), float(match.group(2))


def _section_value(interface: dict[str, Any], section: str) -> Any:
    return interface.get(section)


def _resolve_field(
    interface: dict[str, Any], section: str, field: str, path: str
) -> tuple[list[str], Any]:
    if section not in SECTIONS:
        _fail(path, f"section 必须是 {', '.join(SECTIONS)}")
    root = _section_value(interface, section)
    if root is None:
        _fail(path, f"提取产物不存在 {section} 分区")
    tokens = _pointer_tokens(field, path)
    found, value = _resolve(root, tokens)
    if not found:
        _fail(path, f"{section}{field} 在提取产物中不存在")
    return tokens, value


def _apply_ops(
    interface: dict[str, Any],
    section: str,
    ops: list[Any],
    path: str,
) -> tuple[Any, bool]:
    """在提取基线上应用相对补丁；返回补丁后的分区值和是否有操作。"""

    if section in BODY_SECTIONS:
        other = "data" if section == "json" else "json"
        if section not in interface and other in interface:
            _fail(path, f"提取产物使用 {other} 请求体，不能对 {section} 打补丁")
        if section not in interface:
            _fail(path, f"提取产物不存在 {section} 分区")
    elif section not in interface:
        _fail(path, f"提取产物不存在 {section} 分区")
    base = deepcopy(interface[section])
    if not isinstance(base, (dict, list)):
        _fail(path, f"{section} 分区必须是对象或数组")
    current = base
    for index, raw in enumerate(ops):
        op_path = f"{path}[{index}]"
        op = _object(raw, op_path)
        if set(op) - {"op", "path", "value"}:
            _fail(op_path, "只支持 op/path/value")
        name = op.get("op")
        if name not in {"add", "remove", "replace"}:
            _fail(op_path, "op 必须是 add/remove/replace")
        tokens = _pointer_tokens(op.get("path"), f"{op_path}.path")
        if section == "path_params" and len(tokens) != 1:
            _fail(op_path, "path_params 补丁路径必须指向单个参数")
        parent_found, parent = _resolve(current, tokens[:-1])
        if not parent_found:
            _fail(op_path, "补丁父容器不存在")
        last = tokens[-1]
        if name == "remove":
            if "value" in op:
                _fail(op_path, "remove 操作不能携带 value")
            if section == "path_params":
                _fail(op_path, "路径参数不能删除；请用 replace 设计非法参数值")
            if isinstance(parent, dict):
                if last not in parent:
                    _fail(op_path, "remove 目标不存在")
                del parent[last]
            elif isinstance(parent, list):
                if not last.isdigit() or int(last) >= len(parent):
                    _fail(op_path, "remove 数组索引越界")
                parent.pop(int(last))
            else:
                _fail(op_path, "补丁目标不是对象或数组")
            continue
        if "value" not in op:
            _fail(op_path, f"{name} 操作必须携带 value")
        value = deepcopy(op["value"])
        if isinstance(parent, dict):
            if name == "add" and last not in parent:
                _fail(op_path, "add 目标字段在提取产物中不存在，不能编造字段")
            if name == "replace" and last not in parent:
                _fail(op_path, "replace 目标不存在")
            parent[last] = value
        elif isinstance(parent, list):
            if last == "-":
                if name != "add":
                    _fail(op_path, "只有 add 支持 - 索引")
                parent.append(value)
            elif (
                not last.isdigit()
                or int(last) > len(parent)
                or (name == "replace" and int(last) >= len(parent))
            ):
                _fail(op_path, "数组索引越界")
            else:
                index_value = int(last)
                if name == "add":
                    parent.insert(index_value, value)
                else:
                    parent[index_value] = value
        else:
            _fail(op_path, "补丁目标不是对象或数组")
    return current, True


def _collect_required(
    interface: dict[str, Any],
) -> list[tuple[str, str, str]]:
    """按提取分区顺序收集必传字段：(section, field, description)。"""

    rows: list[tuple[str, str, str]] = []

    def walk(section: str, value: Any, tokens: list[str]) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                walk(section, item, [*tokens, str(key)])
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                walk(section, item, [*tokens, str(index)])
            return
        if _required(value):
            field = "/" + "/".join(token.replace("~", "~0").replace("/", "~1") for token in tokens)
            rows.append((section, field, _description(value)))

    for section in ("headers", "path_params", "query", "json", "data"):
        if section in interface:
            walk(section, interface[section], [])
    return rows


def _collect_optional(interface: dict[str, Any]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []

    def walk(section: str, value: Any, tokens: list[str]) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                walk(section, item, [*tokens, str(key)])
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                walk(section, item, [*tokens, str(index)])
            return
        if not _required(value):
            field = "/" + "/".join(token.replace("~", "~0").replace("/", "~1") for token in tokens)
            rows.append((section, field))

    for section in ("headers", "path_params", "query", "json", "data"):
        if section in interface:
            walk(section, interface[section], [])
    return rows


def _case_path(interface_name: str, index: int) -> str:
    return f"interfaces.{interface_name}.cases[{index}]"


def _validate_assertion(raw: Any, path: str) -> dict[str, Any]:
    item = _object(raw, path)
    if set(item) - {"assertSource", "targetExpr", "comparator", "expectedValue"}:
        _fail(path, "断言只支持 assertSource/targetExpr/comparator/expectedValue")
    source = item.get("assertSource")
    if source not in ASSERT_SOURCES:
        _fail(path, "assertSource 不允许为 status_code，且必须是受支持的来源")
    target = _text(item.get("targetExpr", ""), f"{path}.targetExpr", minimum=0, maximum=512)
    comparator = item.get("comparator")
    if comparator not in COMPARATORS:
        _fail(path, "comparator 不受支持")
    expected = item.get("expectedValue")
    if not isinstance(expected, str):
        _fail(path, "expectedValue 必须是字符串")
    return {
        "assertSource": source,
        "targetExpr": target,
        "comparator": comparator,
        "expectedValue": expected,
    }


def _resolve_response_path(response: Any, target: str, path: str) -> None:
    if not _JSON_PATH.match(target):
        _fail(path, "body_jsonpath 只支持 $ 开头的简单路径")
    tokens = re.findall(r"\.([A-Za-z0-9_-]+)|\[(\d+)\]", target)
    flat = [key or index for key, index in tokens]
    found, _ = _resolve(response, flat)
    if not found:
        _fail(path, "断言字段不在提取产物的响应中")


def _validate_expected(
    raw: Any,
    path: str,
    *,
    category: str,
    response: Any,
) -> dict[str, Any]:
    expected = _object(raw, path)
    if set(expected) - {"statusClass", "assertions"}:
        _fail(path, "expected 只支持 statusClass/assertions")
    status_class = expected.get("statusClass")
    if status_class not in STATUS_CLASSES:
        _fail(path, "statusClass 必须是 2xx 或 4xx")
    assertions = _array(expected.get("assertions"), f"{path}.assertions")
    normalized = [
        _validate_assertion(item, f"{path}.assertions[{index}]")
        for index, item in enumerate(assertions)
    ]
    if len(normalized) > 2:
        _fail(path, "2xx 用例最多 2 条断言")
    if status_class == "4xx" and normalized:
        _fail(path, "4xx 用例不允许业务断言")
    if status_class == "2xx" and normalized:
        if response is None:
            _fail(path, "提取产物没有响应字段，不能声明业务断言")
        for index, item in enumerate(normalized):
            if item["assertSource"] == "body_jsonpath":
                _resolve_response_path(response, item["targetExpr"], f"{path}.assertions[{index}]")
    if category == "negative" and status_class != "4xx":
        _fail(path, "反向用例必须预期 4xx")
    if category == "positive" and status_class != "2xx":
        _fail(path, "正向用例必须预期 2xx")
    return {"statusClass": status_class, "assertions": normalized}


def _validate_basis(
    raw: Any,
    path: str,
    interface: dict[str, Any],
) -> tuple[dict[str, Any], Any]:
    basis = _object(raw, path)
    if set(basis) - {"kind", "section", "field", "constraint"}:
        _fail(path, "basis 只支持 kind/section/field/constraint")
    kind = basis.get("kind")
    if kind not in BASIS_KINDS:
        _fail(path, "kind 必须是 positive/required/constraint/type")
    section = basis.get("section")
    field = basis.get("field")
    constraint = basis.get("constraint")
    if (
        not isinstance(section, str)
        or not isinstance(field, str)
        or not isinstance(constraint, str)
    ):
        _fail(path, "section/field/constraint 必须是字符串")
    if kind == "positive":
        if section or field or constraint:
            _fail(path, "positive 依据的 section/field/constraint 必须为空")
        return {"kind": kind, "section": "", "field": "", "constraint": ""}, None
    _, value = _resolve_field(interface, section, field, path)
    if kind == "required":
        if constraint != "required":
            _fail(path, "required 依据的 constraint 必须是 required")
        if not _required(value):
            _fail(path, "字段在提取产物中未标记必传")
    elif kind == "constraint":
        if not constraint:
            _fail(path, "constraint 依据必须提供约束原文")
        if not _constraint_matches(value, constraint):
            _fail(path, "字段描述不包含该约束")
    else:
        if not constraint:
            _fail(path, "type 依据必须提供类型名")
        if _declared_type(value).casefold() != constraint.casefold():
            _fail(path, "字段类型与 type 依据不一致")
    return {
        "kind": kind,
        "section": section,
        "field": field,
        "constraint": constraint,
    }, value


def _validate_patch(
    raw: Any,
    path: str,
    interface: dict[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    if raw is None:
        return {}, {}
    patch = _object(raw, path)
    if set(patch) - set(SECTIONS):
        _fail(path, f"patch 只支持 {', '.join(SECTIONS)}")
    if "json" in patch and "data" in patch:
        _fail(path, "patch 不能同时包含 json 和 data")
    normalized: dict[str, list[dict[str, Any]]] = {}
    patched: dict[str, Any] = {}
    for section, raw_ops in patch.items():
        ops = _array(raw_ops, f"{path}.{section}")
        if not ops:
            _fail(f"{path}.{section}", "补丁操作不能为空")
        normalized[section] = []
        for index, item in enumerate(ops):
            op = _object(item, f"{path}.{section}[{index}]")
            if set(op) - {"op", "path", "value"}:
                _fail(f"{path}.{section}[{index}]", "只支持 op/path/value")
            normalized[section].append(deepcopy(op))
        patched[section], _ = _apply_ops(
            interface, section, normalized[section], f"{path}.{section}"
        )
    return normalized, patched


def _patch_ops(patch: dict[str, list[dict[str, Any]]], section: str) -> list[dict[str, Any]]:
    return patch.get(section, [])


def _all_patch_ops(patch: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [op for ops in patch.values() for op in ops]


def _single_value_op(
    patch: dict[str, list[dict[str, Any]]],
    section: str,
    field: str,
    path: str,
    *,
    allowed: set[str],
) -> Any:
    matches = [
        op
        for op in _patch_ops(patch, section)
        if op.get("path") == field and op.get("op") in allowed
    ]
    if len(matches) != 1:
        _fail(path, f"补丁必须在 {section}{field} 上包含一个 {sorted(allowed)} 操作")
    return matches[0].get("value")


def _remove_op(patch: dict[str, list[dict[str, Any]]], section: str, field: str) -> bool:
    return any(
        op.get("path") == field and op.get("op") == "remove" for op in _patch_ops(patch, section)
    )


def _validate_boundary_value(
    path: str,
    constraint: str,
    value: Any,
    status_class: str,
) -> None:
    parsed = _boundary(constraint)
    if parsed is None:
        _fail(path, "边界用例只支持 minimum/maximum/minLength/maxLength 约束")
    name, bound = parsed
    if name in {"min", "max"}:
        if isinstance(value, str):
            name = "minLength" if name == "min" else "maxLength"
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            name = "minimum" if name == "min" else "maximum"
        else:
            _fail(path, "边界补丁值必须是数字或字符串")
    if name in {"minimum", "maximum"}:
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            _fail(path, "数值边界的补丁值必须是数字")
        inside = value >= bound if name == "minimum" else value <= bound
        adjacent = value == bound - 1 if name == "minimum" else value == bound + 1
        if status_class == "2xx":
            if value != bound:
                _fail(path, "边界内用例必须取恰好等于边界值")
        elif inside or (isinstance(value, int) and not adjacent):
            _fail(path, "越界用例必须取边界外相邻值")
    else:
        if not isinstance(value, str):
            _fail(path, "长度边界的补丁值必须是字符串")
        length = len(value)
        inside = length >= bound if name == "minLength" else length <= bound
        adjacent = length == bound - 1 if name == "minLength" else length == bound + 1
        if status_class == "2xx":
            if length != bound:
                _fail(path, "边界内用例必须取恰好等于边界长度")
        elif inside or not adjacent:
            _fail(path, "越界用例必须取边界外相邻长度")


def _validate_case(
    raw: Any,
    path: str,
    interface: dict[str, Any],
) -> dict[str, Any]:
    case = _object(raw, path)
    allowed = {"id", "title", "category", "priority", "intent", "basis", "patch", "expected"}
    if set(case) - allowed:
        _fail(path, "用例包含不支持的字段")
    for key in allowed - {"patch"}:
        if key not in case:
            _fail(path, f"缺少字段 {key}")
    case_id = _text(case["id"], f"{path}.id", maximum=100)
    title = _text(case["title"], f"{path}.title", maximum=120)
    category = case["category"]
    if category not in CATEGORIES:
        _fail(path, "category 必须是 positive/negative/boundary")
    priority = case["priority"]
    if priority not in PRIORITIES:
        _fail(path, "priority 必须是 P0/P1/P2")
    intent = _text(case["intent"], f"{path}.intent", maximum=512)
    basis, field_value = _validate_basis(case["basis"], f"{path}.basis", interface)
    patch, _ = _validate_patch(case.get("patch"), f"{path}.patch", interface)
    expected = _validate_expected(
        case["expected"],
        f"{path}.expected",
        category=category,
        response=interface.get("response"),
    )
    status_class = expected["statusClass"]
    if basis["kind"] == "positive":
        if category != "positive":
            _fail(path, "positive 依据只能用于正向用例")
        for section, ops in patch.items():
            if any(op["op"] != "remove" for op in ops):
                _fail(path, "正向用例只允许删除可选字段")
            for op in ops:
                _, target = _resolve_field(interface, section, op["path"], path)
                if _required(target):
                    _fail(path, "正向用例不能删除必传字段")
    elif basis["kind"] == "required":
        if category != "negative" or status_class != "4xx":
            _fail(path, "必填缺失必须是反向 4xx 用例")
        if not _remove_op(patch, basis["section"], basis["field"]):
            _fail(path, "必填缺失用例必须在对应字段上执行 remove")
        removed = [op for ops in patch.values() for op in ops if op["op"] == "remove"]
        if len(removed) != 1:
            _fail(path, "一次只能缺少一个必填字段")
        if len(_all_patch_ops(patch)) != 1:
            _fail(path, "必填缺失用例只能删除目标字段，不能同时修改其他字段")
    elif basis["kind"] == "type":
        if category != "negative" or status_class != "4xx":
            _fail(path, "类型非法必须是反向 4xx 用例")
        wrong = _single_value_op(
            patch,
            basis["section"],
            basis["field"],
            path,
            allowed={"add", "replace"},
        )
        if len(_all_patch_ops(patch)) != 1:
            _fail(path, "类型非法用例只能修改目标字段")
        if _type_matches(wrong, basis["constraint"]):
            _fail(path, "类型非法用例的补丁值仍符合字段类型")
    else:
        if category == "boundary":
            if status_class not in STATUS_CLASSES:
                _fail(path, "边界用例必须预期 2xx 或 4xx")
            value = _single_value_op(
                patch,
                basis["section"],
                basis["field"],
                path,
                allowed={"add", "replace"},
            )
            if len(_all_patch_ops(patch)) != 1:
                _fail(path, "边界用例只能修改目标字段")
            _validate_boundary_value(path, basis["constraint"], value, status_class)
        elif category == "negative":
            if status_class != "4xx":
                _fail(path, "约束非法必须是反向 4xx 用例")
            patch_value = _single_value_op(
                patch,
                basis["section"],
                basis["field"],
                path,
                allowed={"add", "replace"},
            )
            if len(_all_patch_ops(patch)) != 1:
                _fail(path, "约束非法用例只能修改目标字段")
            enum_values = _enum_values(field_value)
            if enum_values:
                if any(str(item) == str(patch_value) for item in enum_values):
                    _fail(path, "枚举非法用例的补丁值仍在枚举范围内")
            elif _format_value(field_value):
                if not isinstance(patch_value, str):
                    _fail(path, "格式非法用例的补丁值必须是字符串")
            else:
                _fail(path, "约束非法只支持 enum 或 format 约束")
        else:
            _fail(path, "constraint 依据只能用于反向或边界用例")
    return {
        "id": case_id,
        "title": title,
        "category": category,
        "priority": priority,
        "intent": intent,
        "basis": basis,
        "patch": patch,
        "expected": expected,
    }


def _validate_uncovered(
    raw: Any,
    path: str,
    interface: dict[str, Any],
) -> dict[str, Any]:
    item = _object(raw, path)
    if set(item) - {"kind", "section", "field", "constraint", "reason"}:
        _fail(path, "uncovered 包含不支持的字段")
    for key in ("kind", "section", "field", "constraint", "reason"):
        if key not in item:
            _fail(path, f"缺少字段 {key}")
    kind = item["kind"]
    if kind not in UNCOVERED_KINDS:
        _fail(path, "kind 必须是 required/constraint/type")
    section = item["section"]
    field = item["field"]
    constraint = item["constraint"]
    if not all(isinstance(value, str) for value in (section, field, constraint)):
        _fail(path, "section/field/constraint 必须是字符串")
    reason = item["reason"]
    if reason not in UNCOVERED_REASONS:
        _fail(path, "reason 不受支持")
    _, value = _resolve_field(interface, section, field, path)
    if kind == "required":
        if constraint != "required" or not _required(value):
            _fail(path, "uncovered 必填引用无效")
    elif kind == "constraint":
        if not constraint or not _constraint_matches(value, constraint):
            _fail(path, "uncovered 约束引用无效")
    elif _declared_type(value).casefold() != constraint.casefold():
        _fail(path, "uncovered 类型引用无效")
    return {
        "kind": kind,
        "section": section,
        "field": field,
        "constraint": constraint,
        "reason": reason,
    }


def _same_reference(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left["kind"] == right["kind"]
        and left["section"] == right["section"]
        and left["field"] == right["field"]
        and _normalized(left["constraint"]) == _normalized(right["constraint"])
    )


def _validate_interface(
    name: str,
    raw: Any,
    baseline: dict[str, Any],
) -> dict[str, Any]:
    path = f"interfaces.{name}"
    item = _object(raw, path)
    if set(item) - {"method", "path", "cases", "uncovered"}:
        _fail(path, "接口设计包含不支持的字段")
    method = item.get("method")
    if not isinstance(method, str) or method != baseline.get("method"):
        _fail(path, "method 必须与提取产物一致")
    route = item.get("path")
    if not isinstance(route, str) or route != baseline.get("path"):
        _fail(path, "path 必须与提取产物一致")
    cases = _array(item.get("cases"), f"{path}.cases")
    if not cases:
        _fail(f"{path}.cases", "接口用例不能为空")
    normalized_cases = [
        _validate_case(case, _case_path(name, index), baseline) for index, case in enumerate(cases)
    ]
    uncovered_raw = item.get("uncovered", [])
    uncovered = [
        _validate_uncovered(row, f"{path}.uncovered[{index}]", baseline)
        for index, row in enumerate(_array(uncovered_raw, f"{path}.uncovered"))
    ]

    positives = [case for case in normalized_cases if case["category"] == "positive"]
    if not positives:
        _fail(path, "每个接口至少需要一条正向用例")
    if not any(not case["patch"] for case in positives):
        _fail(path, "每个接口至少需要一条全参数正向用例")
    optional = _collect_optional(baseline)
    if optional and not any(
        case["patch"] and all(op["op"] == "remove" for ops in case["patch"].values() for op in ops)
        for case in positives
    ):
        _fail(path, "存在可选字段时需要一条仅必填最小参数正向用例")

    required_fields = _collect_required(baseline)
    required_cases = [case for case in normalized_cases if case["basis"]["kind"] == "required"]
    if len(required_cases) > 3:
        _fail(path, "每个接口最多 3 条必填缺失用例")
    if not required_fields and required_cases:
        _fail(path, "没有必传字段时不能设计必填缺失用例")
    if required_fields and not required_cases:
        _fail(path, "存在必传字段时至少需要一条必填缺失用例")
    covered_required = {
        (case["basis"]["section"], case["basis"]["field"]) for case in required_cases
    }
    required_refs = {(section, field) for section, field, _ in required_fields}
    missing_required = required_refs - covered_required
    if missing_required and len(required_fields) <= 3:
        _fail(path, "每个必传字段都需要一条必填缺失用例")
    if not missing_required and len(required_fields) > 3 and len(required_cases) != 3:
        _fail(path, "必传字段超过 3 个时必须取前 3 个字段设计缺失用例")
    uncovered_required = {
        (row["section"], row["field"]) for row in uncovered if row["kind"] == "required"
    }
    if len(required_fields) > 3 and missing_required - uncovered_required:
        _fail(path, "超出上限的必填约束必须写入 uncovered")

    type_cases = [case for case in normalized_cases if case["basis"]["kind"] == "type"]
    if len(type_cases) > 1:
        _fail(path, "每个接口最多 1 条类型非法用例")
    enum_format_cases = [
        case
        for case in normalized_cases
        if case["basis"]["kind"] == "constraint"
        and case["category"] == "negative"
        and (
            _enum_values(
                _resolve_field(
                    baseline,
                    case["basis"]["section"],
                    case["basis"]["field"],
                    path,
                )[1]
            )
            or _format_value(
                _resolve_field(
                    baseline,
                    case["basis"]["section"],
                    case["basis"]["field"],
                    path,
                )[1]
            )
        )
    ]
    if len(enum_format_cases) > 2:
        _fail(path, "枚举与格式非法合计最多 2 条")

    boundary_groups: dict[tuple[str, str, str], set[str]] = {}
    for case in normalized_cases:
        if case["category"] != "boundary":
            continue
        constraint = case["basis"]["constraint"]
        if _boundary(constraint) is None:
            _fail(path, "边界用例只支持 minimum/maximum/minLength/maxLength 约束")
        key = (case["basis"]["section"], case["basis"]["field"], _normalized(constraint))
        boundary_groups.setdefault(key, set()).add(case["expected"]["statusClass"])
    if len(boundary_groups) > 2:
        _fail(path, "每个接口最多选择 2 个约束做边界")
    for statuses in boundary_groups.values():
        if statuses != {"2xx", "4xx"}:
            _fail(path, "每个边界约束必须同时包含边界内 2xx 和越界 4xx 用例")

    covered_refs = [
        {
            "kind": case["basis"]["kind"],
            "section": case["basis"]["section"],
            "field": case["basis"]["field"],
            "constraint": case["basis"]["constraint"],
        }
        for case in normalized_cases
        if case["basis"]["kind"] != "positive"
    ]
    for row in uncovered:
        if any(_same_reference(row, covered) for covered in covered_refs):
            _fail(path, f"uncovered 引用已被用例覆盖：{row['field']}")

    return {
        "method": method,
        "path": route,
        "cases": normalized_cases,
        "uncovered": uncovered,
    }


def validate_design_object(
    design: Any,
    extraction: dict[str, Any],
) -> dict[str, Any]:
    """校验完整或分批设计对象，返回规范化结构。"""

    if not isinstance(design, dict):
        _fail("design", "顶层必须是 JSON 对象")
    if set(design) - {"schemaVersion", "interfaces"}:
        _fail("design", "顶层只支持 schemaVersion 和 interfaces")
    if design.get("schemaVersion") != DESIGN_SCHEMA_VERSION:
        _fail("schemaVersion", f"必须是 {DESIGN_SCHEMA_VERSION}")
    interfaces = _object(design.get("interfaces"), "interfaces")
    if not interfaces:
        _fail("interfaces", "不能为空")
    expected = set(extraction)
    actual = set(interfaces)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        _fail(
            "interfaces",
            f"接口集合必须与提取产物一致（缺少 {missing or '无'}，多出 {extra or '无'}）",
        )
    ids: dict[str, str] = {}
    titles: dict[str, str] = {}
    normalized: dict[str, Any] = {}
    for name, raw in interfaces.items():
        baseline = extraction[name]
        if not isinstance(baseline, dict):
            _fail(f"interfaces.{name}", "提取产物接口配置必须是对象")
        item = _validate_interface(name, raw, baseline)
        for case in item["cases"]:
            if case["id"] in ids:
                _fail(
                    f"interfaces.{name}",
                    f"用例 id 重复：{case['id']}（已用于 {ids[case['id']]}）",
                )
            ids[case["id"]] = name
            folded = case["title"].strip().casefold()
            if folded in titles:
                _fail(
                    f"interfaces.{name}",
                    f"用例 title 重复：{case['title']}（已用于 {titles[folded]}）",
                )
            titles[folded] = name
        normalized[name] = item
    return {"schemaVersion": DESIGN_SCHEMA_VERSION, "interfaces": normalized}


def validate_design_json(raw: str, extraction: dict[str, Any]) -> dict[str, Any]:
    design = parse_design_json(raw)
    return validate_design_object(design, extraction)


def canonical_design(design: dict[str, Any]) -> str:
    return json.dumps(design, ensure_ascii=False)


def pointer_tokens(pointer: Any, path: str = "path") -> list[str]:
    """公开的相对 JSON Pointer 解析，供生成对齐校验复用。"""

    return _pointer_tokens(pointer, path)


def resolve_pointer(root: Any, tokens: list[str]) -> tuple[bool, Any]:
    """按已解析的令牌定位值，返回 (是否存在, 父容器)。"""

    return _resolve(root, tokens)
