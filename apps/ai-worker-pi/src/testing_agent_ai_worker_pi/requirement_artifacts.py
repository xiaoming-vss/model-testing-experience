"""Validate versioned requirement artifacts and their source/operation references.

Kept identical in both independently deployable Python applications; the schemas
are also distributed with each app and the two default skills.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

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


class ArtifactReferenceError(ValueError):
    """Schema-valid artifact with all independently checkable reference issues."""

    def __init__(self, artifact: dict[str, Any], issues: list[str]) -> None:
        self.artifact = artifact
        self.issues = list(dict.fromkeys(issues))
        super().__init__("\n".join(self.issues))


def _problem(message, errors):
    if errors is None:
        raise ValueError(message)
    errors.append(message)


def _index(items, label, errors=None):
    result = {}
    for item in items:
        if item["id"] in result:
            _problem(f"{label}: ID 重复 {item['id']}", errors)
        result[item["id"]] = item
    return result


def _subset(values, available, label, errors=None):
    missing = sorted(set(values) - set(available))
    if missing:
        _problem(f"{label}: 引用了不存在的条目 {missing}", errors)


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


def validate_artifact(
    value: str | dict[str, Any], kind: str, *, allow_resolved_questions: bool = False
) -> dict[str, Any]:
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
    version = value.get("schemaVersion")
    if not isinstance(version, str):
        raise ValueError("需求产物 schemaVersion 必须是字符串")
    error = next(
        _validator(kind, allow_resolved_questions).iter_errors(value),
        None,
    )
    if error:
        path = ".".join(str(part) for part in error.absolute_path) or "$"
        raise ValueError(f"需求产物字段不符合契约 ({path}): {error.message}")
    errors: list[str] = []
    sources = _index(value["sources"], "sources", errors)
    evidence = _index(value.get("evidence", []), "evidence", errors)
    _subset([item["sourceId"] for item in evidence.values()], sources, "evidence.sourceId", errors)
    questions = _index(value["questions"], "questions", errors)
    for item in _walk(value):
        if kind == "requirement_understanding":
            ids = item.get("evidenceIds", [])
            _subset(ids, evidence, "evidenceIds", errors)
            references = [evidence[eid] for eid in ids if eid in evidence]
        else:
            references = item.get("sourceReferences", [])
        _subset(
            [r["sourceId"] for r in references],
            sources,
            "evidence.sourceId" if kind == "requirement_understanding" else "sourceReferences",
            errors,
        )
        _subset(item.get("relatedQuestionIds", []), questions, "relatedQuestionIds", errors)
        is_fact = "value" in item and not isinstance(item["value"], dict)
        status = item.get("confirmationStatus", "confirmed" if is_fact else None)
        if (
            status == "confirmed"
            and references
            and all(sources.get(r["sourceId"], {}).get("type") == "example" for r in references)
        ):
            _problem("示例来源不能单独支撑已确认事实", errors)
        if status == "conflicting" and any(
            questions[q]["status"] != "open" for q in item["relatedQuestionIds"] if q in questions
        ):
            _problem("冲突事实必须关联未解决问题", errors)
    if kind == "document_extraction":
        try:
            targets = _check_extraction(value)
        except ValueError as exc:
            errors.append(str(exc))
            raise ArtifactReferenceError(value, errors) from exc
    else:
        targets = _check_understanding(value, errors)
    for question in questions.values():
        if question["status"] == "resolved" and (
            not isinstance(question.get("answer"), dict)
            or question["answer"].get("confirmationStatus", "confirmed") != "confirmed"
        ):
            _problem("历史已解决问题必须有带来源的明确答复", errors)
        for target in question["affectedRefs"]:
            if target["id"] not in targets.get(target["kind"], {}):
                _problem("questions.affectedRefs: 引用了不存在的条目", errors)
    if errors:
        raise ArtifactReferenceError(value, errors)
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


def _check_understanding(value, errors):
    modules = _index(value["modules"], "modules", errors=errors)
    if not modules and not any(
        q["status"] == "open" and {"kind": "requirement", "id": "requirement"} in q["affectedRefs"]
        for q in value["questions"]
    ):
        _problem("尚未识别模块时需保留整体需求范围问题，不能填占位模块", errors)
    operations = _index(
        [o for m in modules.values() for o in m["operations"]], "operations", errors=errors
    )
    controls = _index(
        [c for o in operations.values() for c in o["interaction"]["controls"]],
        "controls",
        errors=errors,
    )
    entries = _index(
        [e for m in modules.values() for e in m.get("entryPoints", [])],
        "entryPoints",
        errors=errors,
    )
    rules = _index(value["businessRules"], "businessRules", errors=errors)
    flows = _index(value["businessFlows"], "businessFlows", errors=errors)
    owners = {o["id"]: m["id"] for m in modules.values() for o in m["operations"]}
    for module in modules.values():
        local = {o["id"] for o in module["operations"]}
        _subset(
            [s["operationId"] for s in module.get("userVisibleFlow", [])],
            local,
            "userVisibleFlow",
            errors=errors,
        )
    for operation in operations.values():
        _index(operation["steps"], "operation.steps", errors=errors)
        _subset(operation.get("ruleIds", []), rules, "operation.ruleIds", errors=errors)
        for rid in operation.get("ruleIds", []):
            if rid in rules and operation["id"] not in rules[rid]["operationIds"]:
                _problem(f"操作与规则引用不一致: {operation['id']} → {rid}.operationIds", errors)
    for control in controls.values():
        _index(control["options"]["items"], "control.options", errors=errors)
        completeness = control["options"]["completeness"]
        if completeness["value"] == "unknown" and completeness.get(
            "confirmationStatus", "confirmed"
        ) not in {
            "unconfirmed",
            "conflicting",
        }:
            _problem("未知选项完整性不能标记为已确认", errors)
    for rule in rules.values():
        _subset(rule["moduleIds"], modules, "rule.moduleIds", errors=errors)
        _subset(rule["operationIds"], operations, "rule.operationIds", errors=errors)
        if any(owners.get(oid) not in rule["moduleIds"] for oid in rule["operationIds"]):
            _problem("规则关联操作不属于关联模块", errors)
    for flow in flows.values():
        _subset(flow["moduleIds"], modules, "flow.moduleIds", errors=errors)
        steps = _index(flow["steps"], "flow.steps", errors=errors)
        for step in steps.values():
            if (
                step["moduleId"] not in flow["moduleIds"]
                or owners.get(step["operationId"]) != step["moduleId"]
            ):
                _problem("流程引用的模块和操作不一致", errors)
            for branch in step["nextSteps"]:
                _subset(
                    branch.get("conditionRuleIds", []), rules, "conditionRuleIds", errors=errors
                )
            _subset(
                [s["stepId"] for s in step["nextSteps"] if s["stepId"] is not None],
                steps,
                "flow.nextSteps",
                errors=errors,
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
