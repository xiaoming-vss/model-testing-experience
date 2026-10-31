"""Compile reusable authoring inputs without runtime variables or model calls."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any
from urllib.parse import quote as quote_url

VERSION = "ui_yaml_draft/2.0"
IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
REFERENCE = re.compile(r"\{\{data\.([A-Za-z][A-Za-z0-9_]*)\.([A-Za-z][A-Za-z0-9_]*)(\|xpath)?\}\}")
CASE_METADATA = {"draftVersion", "dataRequirements", "designConflicts"}
STEP_METADATA = {"dataBindings", "sourceRefs", "purpose"}


def xpath_literal(value: str) -> str:
    if "'" not in value:
        return "'" + value + "'"
    if '"' not in value:
        return '"' + value + '"'
    return (
        "concat("
        + ", ".join(
            "'" + part + "'" if i % 2 == 0 else '"\'"'
            for i, part in enumerate(re.split("(')", value))
        )
        + ")"
    )


def requirements(case: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = case.get("dataRequirements", [])
    if not isinstance(rows, list):
        raise ValueError("dataRequirements 必须是数组")
    result = {}
    signatures = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "id",
            "title",
            "fields",
            "conditions",
            "confirmed",
        }:
            raise ValueError("待补数据需要 id/title/fields/conditions/confirmed")
        key = row["id"]
        if not isinstance(key, str) or not IDENTIFIER.fullmatch(key) or key in result:
            raise ValueError("待补数据 id 必须是唯一英文标识")
        if not isinstance(row["title"], str) or not row["title"].strip():
            raise ValueError("待补数据必须有明确名称")
        fields, conditions = row["fields"], row["conditions"]
        if not isinstance(fields, dict) or not isinstance(conditions, list):
            raise ValueError("待补数据 fields 必须是对象、conditions 必须是数组")
        if not fields and not conditions:
            raise ValueError("待补数据必须说明字段或准备条件")
        if any(not isinstance(c, str) or not c.strip() for c in conditions):
            raise ValueError("准备条件必须是非空说明")
        if not isinstance(row["confirmed"], bool):
            raise ValueError("confirmed 必须是布尔值")
        for name, field in fields.items():
            if not isinstance(name, str) or not IDENTIFIER.fullmatch(name):
                raise ValueError("数据字段名必须是英文标识")
            if not isinstance(field, dict) or set(field) != {"label", "value"}:
                raise ValueError("数据字段必须包含 label/value")
            if not isinstance(field["label"], str) or not field["label"].strip():
                raise ValueError("数据字段 label 不能为空")
            if field["value"] is not None and (
                not isinstance(field["value"], str) or not field["value"].strip()
            ):
                raise ValueError("数据值必须为非空字符串或 null")
        signature = (row["title"].strip(), tuple(sorted(fields)))
        if signature in signatures:
            raise ValueError("同一份数据重复声明，请合并并复用引用")
        signatures.add(signature)
        result[key] = row
    return result


def render_binding(
    template: str, data: dict[str, dict[str, Any]], *, xpath: bool, url: bool = False
) -> str | None:
    if not isinstance(template, str) or not template.strip():
        raise ValueError("dataBindings 模板必须是非空字符串")
    matches = list(REFERENCE.finditer(template))
    if not matches or "{{data." in REFERENCE.sub("", template):
        raise ValueError("模板必须使用 {{data.数据ID.字段名}} 引用")
    pending = False

    def replace(match: re.Match[str]) -> str:
        nonlocal pending
        key, field, mode = match.groups()
        if xpath:
            quote = None
            for char in template[: match.start()]:
                if quote is None and char in "\"'":
                    quote = char
                elif char == quote:
                    quote = None
            if quote is not None:
                raise ValueError("|xpath 引用不能放在引号内，编译器会添加安全引号")
        if key not in data or field not in data[key]["fields"]:
            raise ValueError(f"未定义的数据引用: {key}.{field}")
        if xpath != bool(mode):
            raise ValueError("XPath 定位的数据引用必须使用 |xpath，其他字段使用原值引用")
        value = data[key]["fields"][field]["value"]
        if value is None:
            pending = True
            return ""
        if xpath:
            return xpath_literal(value)
        return quote_url(value, safe="") if url and "?" in template[: match.start()] else value

    rendered = REFERENCE.sub(replace, template)
    return None if pending else rendered


def compile_case(
    case: dict[str, Any], *, complete: bool = False, for_validation: bool = False
) -> dict[str, Any]:
    if not isinstance(case, dict):
        raise ValueError("用例必须是对象")
    result = deepcopy(case)
    version = result.get("draftVersion")
    raw_steps = result.get("stepsJson")
    inspected_steps = raw_steps if isinstance(raw_steps, list) else []
    has_metadata = bool(CASE_METADATA.intersection(result)) or any(
        STEP_METADATA.intersection(step) for step in inspected_steps if isinstance(step, dict)
    )
    if not has_metadata:
        return result
    if version != VERSION:
        raise ValueError("新增补全字段需要 draftVersion: ui_yaml_draft/2.0")
    if not isinstance(raw_steps, list):
        raise ValueError("stepsJson 必须是数组")
    data = requirements(result)
    conflicts = result.get("designConflicts", [])
    if not isinstance(conflicts, list):
        raise ValueError("designConflicts 必须是数组")
    for conflict in conflicts:
        if not isinstance(conflict, dict) or set(conflict) != {
            "sourceRefs",
            "reason",
            "requiredCapability",
        }:
            raise ValueError("设计冲突必须包含 sourceRefs/reason/requiredCapability")
        if (
            not isinstance(conflict["sourceRefs"], list)
            or not conflict["sourceRefs"]
            or not all(isinstance(r, str) and r for r in conflict["sourceRefs"])
        ):
            raise ValueError("设计冲突需要对应的来源引用")
        if any(
            not isinstance(conflict[k], str) or not conflict[k].strip()
            for k in ("reason", "requiredCapability")
        ):
            raise ValueError("设计冲突需要具体原因和所需能力")
    if complete:
        if conflicts:
            raise ValueError("存在未解决的设计冲突，不能导入或执行")
        for row in data.values():
            if any(f["value"] is None for f in row["fields"].values()) or (
                row["conditions"] and not row["confirmed"]
            ):
                raise ValueError(f"待补数据「{row['title']}」尚未填全或确认准备条件")
    for index, step in enumerate(result.get("stepsJson", []), 1):
        if not isinstance(step, dict):
            raise ValueError("步骤必须是对象")
        bindings = step.get("dataBindings", {})
        if not isinstance(bindings, dict) or set(bindings) - {"locatorValue", "operationValue"}:
            raise ValueError("dataBindings 仅支持 locatorValue/operationValue")
        for field in ("locatorValue", "operationValue"):
            inline = step.get(field)
            if isinstance(inline, str) and re.search(r"\{\{\s*data\.", inline):
                if field in bindings and bindings[field] != inline:
                    raise ValueError("字段内数据模板与 dataBindings 不一致，请只保留一个模板定义")
                bindings[field] = inline
                step["dataBindings"] = bindings
        legacy = step.get("missingFields", [])
        if not isinstance(legacy, list):
            raise ValueError("missingFields 必须是数组")
        for entry in legacy:
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("fields"), list)
                or not all(isinstance(field, str) for field in entry["fields"])
            ):
                raise ValueError("missingFields 每项的 fields 必须是字符串数组")
        legacy_fields = {field for entry in legacy for field in entry["fields"]}
        if legacy_fields.intersection(bindings):
            raise ValueError("数据引用已说明缺口，不能重复添加同字段 missingFields")
        if bindings and step.get("locatorType") == "css" and "locatorValue" in bindings:
            raise ValueError("数据关联定位请使用带 |xpath 转义的 XPath，不能拼接未转义 CSS")
        for field, template in bindings.items():
            value = render_binding(
                template,
                data,
                xpath=field == "locatorValue" and step.get("locatorType") == "xpath",
                url=field == "operationValue" and step.get("keyword") == "open",
            )
            step[field] = value
            if value is None:
                if complete:
                    raise ValueError(f"步骤 {index} 的 {field} 仍有未填数据")
                if for_validation:
                    step.setdefault("missingFields", []).append(
                        dict(
                            fields=[field],
                            operation="补充关联数据",
                            target=field,
                            value=None,
                            reason="数据引用尚未填全",
                        )
                    )
        if complete and step.get("missingFields"):
            raise ValueError(f"步骤 {index} 仍有独立字段缺口")
        if complete or for_validation:
            for key in STEP_METADATA:
                step.pop(key, None)
    if complete or for_validation:
        for key in CASE_METADATA:
            result.pop(key, None)
    return result
