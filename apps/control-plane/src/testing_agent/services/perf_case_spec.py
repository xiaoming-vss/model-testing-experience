"""Safe YAML parsing and early structural validation for performance cases.

The worker remains the authority for full RunSpec validation. The control plane
rejects malformed or platform-conflicting YAML before freezing a run snapshot.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

from testing_agent.core.errors import ErrPerfCaseYamlInvalid, dynamic_error

MAX_CASE_YAML_BYTES = 512 * 1024
_ALLOWED_TOP_LEVEL = {"specVersion", "case"}
_ALLOWED_CASE_KEYS = {"name", "steps", "load", "acceptance", "data"}
_RESERVED_TOP_LEVEL = {"runId", "projectId", "environment", "remoteWrite", "limits"}
_DATA_SOURCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.(csv|json)$")
_LOAD_MODELS = {"vus", "arrival_rate", "request_rate", "staged_vus"}
_LOAD_MODEL_NAMES = "vus/arrival_rate/request_rate/staged_vus"
_STAGED_PROFILES = {"step", "spike", "custom"}
_ACCEPTANCE_SOURCES = {"user_confirmed", "model_suggested", "missing"}


class _CaseLoader(yaml.SafeLoader):
    """SafeLoader without aliases and with duplicate-key rejection."""

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(yaml.AliasEvent):
            raise ValueError("YAML 不允许使用别名")
        return super().compose_node(parent, index)

    def construct_mapping(self, node: Any, deep: bool = False) -> dict[Any, Any]:
        if isinstance(node, yaml.MappingNode):
            self.flatten_mapping(node)
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise ValueError("YAML 映射键必须是字符串")
            if key in mapping:
                raise ValueError(f"YAML 重复键: {key}")
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def _invalid(message: str):
    return dynamic_error(ErrPerfCaseYamlInvalid, f"性能用例 YAML 内容不合法: {message}")


def _json_compatible(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _json_compatible(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise _invalid(f"{path} 的键必须是字符串")
            _json_compatible(item, f"{path}.{key}")
        return
    raise _invalid(f"{path} 必须是 JSON 兼容类型")


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _invalid(f"{path} 必须是映射")
    return value


def _require_name(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid(f"{path} 必须是非空字符串")
    return value.strip()


def _validate_data(data: Any) -> list[dict[str, Any]]:
    if data is None:
        return []
    if not isinstance(data, list):
        raise _invalid("case.data 必须是列表")
    names: set[str] = set()
    for index, item in enumerate(data):
        entry = _require_mapping(item, f"case.data[{index}]")
        name = _require_name(entry.get("name"), f"case.data[{index}].name")
        if name in names:
            raise _invalid(f"数据名重复: {name}")
        names.add(name)
        source = entry.get("source")
        rows = entry.get("rows")
        if bool(source) == bool(rows):
            raise _invalid(f"case.data[{index}] 的 source 和 rows 必须二选一")
        if source is not None:
            if not isinstance(source, str) or not _DATA_SOURCE_RE.fullmatch(source):
                raise _invalid(f"case.data[{index}].source 必须是安全的 .csv/.json 文件名")
        if rows is not None:
            if not isinstance(rows, list) or not rows:
                raise _invalid(f"case.data[{index}].rows 必须是非空列表")
            for row_index, row in enumerate(rows):
                row_map = _require_mapping(row, f"case.data[{index}].rows[{row_index}]")
                for key, value in row_map.items():
                    if not isinstance(value, str):
                        raise _invalid(f"case.data[{index}].rows[{row_index}].{key} 必须是字符串")
    return data


def _validate_steps(steps: Any) -> list[dict[str, Any]]:
    if not isinstance(steps, list) or not steps:
        raise _invalid("case.steps 必须是非空列表")
    names: set[str] = set()
    for index, item in enumerate(steps):
        step = _require_mapping(item, f"case.steps[{index}]")
        name = _require_name(step.get("name"), f"case.steps[{index}].name")
        if name in names:
            raise _invalid(f"步骤名称重复: {name}")
        names.add(name)
        if not isinstance(step.get("method"), str) or not step["method"].strip():
            raise _invalid(f"case.steps[{index}].method 必须是非空字符串")
        if not isinstance(step.get("path"), str) or not step["path"].strip():
            raise _invalid(f"case.steps[{index}].path 必须是非空字符串")
        if "expectedStatuses" in step:
            statuses = step["expectedStatuses"]
            if (
                not isinstance(statuses, list)
                or not statuses
                or any(type(value) is not int or not 100 <= value <= 599 for value in statuses)
                or len(set(statuses)) != len(statuses)
            ):
                raise _invalid(f"case.steps[{index}].expectedStatuses 必须是不重复的状态码列表")
    return steps


def _validate_staged_load(load: dict[str, Any]) -> None:
    if "profile" in load and load["profile"] not in _STAGED_PROFILES:
        raise _invalid("case.load.profile 只能是 step/spike/custom")
    stages = load.get("stages")
    if not isinstance(stages, list) or not stages:
        raise _invalid("case.load.stages 必须是非空列表")
    for index, item in enumerate(stages):
        stage = _require_mapping(item, f"case.load.stages[{index}]")
        target = stage.get("target")
        if not isinstance(target, int) or isinstance(target, bool) or target < 1:
            raise _invalid(f"case.load.stages[{index}].target 必须是正整数")
        for key in ("ramp", "hold"):
            if key in stage:
                value = stage[key]
                if not isinstance(value, str) or not value.strip():
                    raise _invalid(f"case.load.stages[{index}].{key} 必须是非空字符串")
    if "finalDown" in load:
        final_down = load["finalDown"]
        if not isinstance(final_down, str) or not final_down.strip():
            raise _invalid("case.load.finalDown 必须是非空字符串")


def parse_case_yaml(raw: str) -> dict[str, Any]:
    if not isinstance(raw, str) or not raw.strip():
        raise _invalid("内容不能为空")
    if len(raw.encode("utf-8")) > MAX_CASE_YAML_BYTES:
        raise _invalid("YAML 超过 512KB 限制")
    if "\x00" in raw:
        raise _invalid("YAML 不能包含 NUL 字符")
    try:
        parsed = yaml.load(raw, Loader=_CaseLoader)
    except (yaml.YAMLError, ValueError) as exc:
        raise _invalid(str(exc)) from None
    root = _require_mapping(parsed, "根节点")
    reserved = sorted(_RESERVED_TOP_LEVEL & set(root))
    if reserved:
        raise _invalid(f"以下平台字段由平台注入，不能在用例中提供: {', '.join(reserved)}")
    unknown = sorted(set(root) - _ALLOWED_TOP_LEVEL)
    if unknown:
        raise _invalid(f"不支持的顶层字段: {', '.join(unknown)}")
    if root.get("specVersion") != "1.0":
        raise _invalid('specVersion 必须是字符串 "1.0"')
    case = _require_mapping(root.get("case"), "case")
    unknown_case = sorted(set(case) - _ALLOWED_CASE_KEYS)
    if unknown_case:
        raise _invalid(f"不支持的 case 字段: {', '.join(unknown_case)}")
    _require_name(case.get("name"), "case.name")
    steps = _validate_steps(case.get("steps"))
    load = _require_mapping(case.get("load"), "case.load")
    model = load.get("model")
    if model not in _LOAD_MODELS:
        raise _invalid(f"case.load.model 必须是 {_LOAD_MODEL_NAMES} 之一")
    if model == "staged_vus":
        _validate_staged_load(load)
    if model == "request_rate" and len(steps) != 1:
        raise _invalid("request_rate 只支持单步骤用例")
    acceptance = _require_mapping(case.get("acceptance"), "case.acceptance")
    source = acceptance.get("source")
    if source not in _ACCEPTANCE_SOURCES:
        raise _invalid("case.acceptance.source 不合法")
    if source == "user_confirmed":
        if acceptance.get("confirmed") is not True:
            raise _invalid("user_confirmed 必须标记 confirmed=true")
        criteria = acceptance.get("criteria")
        if not isinstance(criteria, dict) or not criteria:
            raise _invalid("user_confirmed 必须提供验收标准")
    _validate_data(case.get("data"))
    _json_compatible(root, "root")
    return root


def case_data_sources(parsed: dict[str, Any]) -> set[str]:
    case = parsed.get("case") or {}
    data = case.get("data") or []
    sources: set[str] = set()
    for item in data:
        source = item.get("source") if isinstance(item, dict) else None
        if source:
            sources.add(source)
    return sources
