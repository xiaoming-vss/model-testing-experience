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

TYPES = {"document_extraction"}


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


def _check_finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON 数值必须是有限数值")
    if isinstance(value, dict):
        for child in value.values():
            _check_finite(child)
    elif isinstance(value, list):
        for child in value:
            _check_finite(child)


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
    _check_finite(value)
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
    return _check_readable_material(value)


def _check_readable_material(value: dict[str, Any]) -> dict[str, Any]:
    """Validate the readable material's IDs, hierarchy and evidence links."""
    errors: list[str] = []
    sources = _index(value["sources"], "sources", errors)
    blocks = _index(value["materialBlocks"], "materialBlocks", errors)
    functions = _index(value["functions"], "functions", errors)
    _index(value["questions"], "questions", errors)
    for block in blocks.values():
        _subset([block["sourceId"]], sources, "materialBlocks.sourceId", errors)
        if block["kind"] == "table":
            rows = block["content"]["rows"]
            covered: set[tuple[int, int]] = set()
            for span in block["content"].get("spans", []):
                for row in range(span["row"], span["row"] + span["rowSpan"]):
                    for column in range(span["column"], span["column"] + span["columnSpan"]):
                        if row >= len(rows) or column >= len(rows[row]) or (row, column) in covered:
                            errors.append(f"materialBlocks: {block['id']} 的表格合并区域越界或重叠")
                        covered.add((row, column))
        seen = {block["id"]}
        parent = block["parentId"]
        while parent is not None:
            if parent not in blocks or parent in seen:
                errors.append(f"materialBlocks.parentId: {block['id']} 的父块不存在或层级成环")
                break
            seen.add(parent)
            parent = blocks[parent]["parentId"]
    for function in value["functions"]:
        titles = [section["title"] for section in function["sections"]]
        if len(titles) != len(set(titles)):
            errors.append(f"functions: {function['id']} 的分类重复")
        for section in function["sections"]:
            for item in section["items"]:
                _subset(item["materialBlockIds"], blocks, "functions.materialBlockIds", errors)
    for question in value["questions"]:
        _subset(question["materialBlockIds"], blocks, "questions.materialBlockIds", errors)
        _subset(question["functionIds"], functions, "questions.functionIds", errors)
    if errors:
        raise ArtifactReferenceError(value, errors)
    return value


def serialize_artifact(value, kind):
    return json.dumps(validate_artifact(value, kind), ensure_ascii=False, separators=(",", ":"))


def requirement_content(value):
    """Validate structured material and retain plain-text requirement input."""
    if isinstance(value, dict):
        return serialize_artifact(value, "document_extraction")
    content = str(value or "")
    try:
        parsed = json.loads(content, object_pairs_hook=_pairs, parse_constant=_constant)
    except ValueError:
        if (
            content.lstrip().startswith("{")
            and '"artifactType"' in content
            and "readable_requirement_material" in content
        ):
            raise ValueError("需求材料 JSON 无法解析") from None
        return content
    if isinstance(parsed, dict) and ("artifactType" in parsed or "schemaVersion" in parsed):
        return serialize_artifact(parsed, "document_extraction")
    return content
