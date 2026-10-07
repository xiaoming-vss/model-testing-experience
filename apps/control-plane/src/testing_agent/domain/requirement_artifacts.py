"""Validate versioned requirement artifacts and their source/operation references.

Kept identical in both independently deployable Python applications; the schemas
are also distributed with each app and the two default skills.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

TYPES = {"document_extraction", "requirement_understanding"}


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"重复 JSON 字段: {key}")
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f"非法 JSON 数值: {value}")


@lru_cache(maxsize=4)
def _validator(kind, allow_resolved_questions=False):
    filename = kind.replace("_", "-") + ".schema.json"
    schema = json.loads((Path(__file__).with_name("requirement_schemas") / filename).read_text())
    if allow_resolved_questions:
        # Historical input is read for AI revision; newly written artifacts use open only.
        schema["$defs"]["question"]["properties"]["status"] = {"enum": ["open", "resolved"]}
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _index(items, label):
    result = {}
    for item in items:
        if item["id"] in result:
            raise ValueError(f"{label}: ID 重复 {item['id']}")
        result[item["id"]] = item
    return result


def _subset(values, available, label):
    if not set(values) <= set(available):
        raise ValueError(f"{label}: 引用了不存在的条目")


def _walk(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON 数值必须是有限数值")
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def validate_artifact(value, kind, *, allow_resolved_questions=False):
    """Return the unchanged parsed object; malformed new JSON never becomes legacy text."""
    if kind not in TYPES:
        raise ValueError("未知需求产物类型")
    if isinstance(value, str):
        try:
            value = json.loads(value, object_pairs_hook=_pairs, parse_constant=_constant)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"需求产物不是合法 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("需求产物必须是 JSON 对象")
    questions_input = value.get("questions")
    if (
        not allow_resolved_questions
        and isinstance(questions_input, list)
        and any(isinstance(q, dict) and q.get("status") == "resolved" for q in questions_input)
    ):
        raise ValueError("已解决问题需先将答复补入对应内容，再从 questions 删除并清理关联引用")
    error = next(_validator(kind, allow_resolved_questions).iter_errors(value), None)
    if error:
        path = ".".join(str(part) for part in error.absolute_path) or "$"
        raise ValueError(f"需求产物字段不符合契约 ({path}): {error.message}")
    sources = _index(value["sources"], "sources")
    questions = _index(value["questions"], "questions")
    for item in _walk(value):
        references = item.get("sourceReferences", [])
        _subset([r["sourceId"] for r in references], sources, "sourceReferences")
        _subset(item.get("relatedQuestionIds", []), questions, "relatedQuestionIds")
        status = item.get("confirmationStatus")
        if (
            status == "confirmed"
            and references
            and all(sources[r["sourceId"]]["type"] == "example" for r in references)
        ):
            raise ValueError("示例来源不能单独支撑已确认事实")
        if status == "conflicting" and any(
            questions[q]["status"] != "open" for q in item["relatedQuestionIds"]
        ):
            raise ValueError("冲突事实必须关联未解决问题")
    if kind == "document_extraction":
        targets = _check_extraction(value)
    else:
        targets = _check_understanding(value)
    for question in questions.values():
        if question["status"] == "resolved" and (
            not isinstance(question["answer"], dict)
            or question["answer"].get("confirmationStatus") != "confirmed"
        ):
            raise ValueError("历史已解决问题必须有带来源的明确答复")
        for target in question["affectedRefs"]:
            if target["id"] not in targets.get(target["kind"], {}):
                raise ValueError("questions.affectedRefs: 引用了不存在的条目")
    return value


def _check_extraction(value):
    blocks = _index(value["contentBlocks"], "contentBlocks")
    facts = _index(value["extractedFacts"], "extractedFacts")
    for block in blocks.values():
        seen = {block["id"]}
        parent = block["parentId"]
        while parent is not None:
            if parent not in blocks or parent in seen:
                raise ValueError("contentBlocks.parentId: 父块不存在或层级成环")
            seen.add(parent)
            parent = blocks[parent]["parentId"]
        if block["kind"] != "table":
            continue
        table, occupied = block["table"], set()
        for cell in table["cells"]:
            for row in range(cell["row"], cell["row"] + cell["rowSpan"]):
                for column in range(cell["column"], cell["column"] + cell["columnSpan"]):
                    if (
                        (table["rowCount"] is not None and row >= table["rowCount"])
                        or (table["columnCount"] is not None and column >= table["columnCount"])
                        or (row, column) in occupied
                    ):
                        raise ValueError("table.cells: 单元格超出范围或合并区域重叠")
                    occupied.add((row, column))
        if block["parseStatus"] == "complete" and (
            table["rowCount"] is None
            or table["columnCount"] is None
            or len(occupied) != table["rowCount"] * table["columnCount"]
            or any(c["text"] is None for c in table["cells"])
        ):
            raise ValueError("完整表格必须有完整行列和已识别单元格")
    for fact in facts.values():
        _subset(fact["relatedBlockIds"], blocks, "extractedFacts.relatedBlockIds")
    return {"block": blocks, "extracted_fact": facts}


def _check_understanding(value):
    modules = _index(value["modules"], "modules")
    if not modules and not any(
        q["status"] == "open" and {"kind": "requirement", "id": "requirement"} in q["affectedRefs"]
        for q in value["questions"]
    ):
        raise ValueError("尚未识别模块时需保留整体需求范围问题，不能填占位模块")
    operations = _index([o for m in modules.values() for o in m["operations"]], "operations")
    controls = _index(
        [c for o in operations.values() for c in o["interaction"]["controls"]], "controls"
    )
    entries = _index([e for m in modules.values() for e in m["entryPoints"]], "entryPoints")
    rules = _index(value["businessRules"], "businessRules")
    flows = _index(value["businessFlows"], "businessFlows")
    owners = {o["id"]: m["id"] for m in modules.values() for o in m["operations"]}
    for module in modules.values():
        local = {o["id"] for o in module["operations"]}
        _subset([s["operationId"] for s in module["userVisibleFlow"]], local, "userVisibleFlow")
    for operation in operations.values():
        _index(operation["steps"], "operation.steps")
        _subset(operation["ruleIds"], rules, "operation.ruleIds")
        for rid in operation["ruleIds"]:
            if operation["id"] not in rules[rid]["operationIds"]:
                raise ValueError("操作与规则引用不一致")
    for control in controls.values():
        _index(control["options"]["items"], "control.options")
        completeness = control["options"]["completeness"]
        if completeness["value"] == "unknown" and completeness["confirmationStatus"] not in {
            "unconfirmed",
            "conflicting",
        }:
            raise ValueError("未知选项完整性不能标记为已确认")
    for rule in rules.values():
        _subset(rule["moduleIds"], modules, "rule.moduleIds")
        _subset(rule["operationIds"], operations, "rule.operationIds")
        if any(owners[oid] not in rule["moduleIds"] for oid in rule["operationIds"]):
            raise ValueError("规则关联操作不属于关联模块")
    for flow in flows.values():
        _subset(flow["moduleIds"], modules, "flow.moduleIds")
        steps = _index(flow["steps"], "flow.steps")
        for step in steps.values():
            if (
                step["moduleId"] not in flow["moduleIds"]
                or owners.get(step["operationId"]) != step["moduleId"]
            ):
                raise ValueError("流程引用的模块和操作不一致")
            _subset(
                [s["stepId"] for s in step["nextSteps"] if s["stepId"] is not None],
                steps,
                "flow.nextSteps",
            )
    return {
        "requirement": {"requirement": value},
        "module": modules,
        "operation": operations,
        "control": controls,
        "entry": entries,
        "rule": rules,
        "flow": flows,
    }


def serialize_artifact(value, kind):
    return json.dumps(validate_artifact(value, kind), ensure_ascii=False, separators=(",", ":"))


def requirement_content(value):
    """Validate new imported requirements while preserving existing text inputs."""
    if isinstance(value, dict):
        return serialize_artifact(value, "requirement_understanding")
    content = str(value or "")
    try:
        parsed = json.loads(content, object_pairs_hook=_pairs, parse_constant=_constant)
    except ValueError:
        # Recognizable new artifact syntax must not fall back after a malformed edit.
        if (
            content.lstrip().startswith("{")
            and '"artifactType"' in content
            and "requirement_understanding" in content
        ):
            raise ValueError("需求理解 JSON 无法解析") from None
        return content
    if isinstance(parsed, dict) and ("artifactType" in parsed or "schemaVersion" in parsed):
        return serialize_artifact(parsed, "requirement_understanding")
    return content
