"""Validate the new test-scope artifact without changing historical formats."""

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = json.loads(
        (Path(__file__).parent / "requirement_schemas/test-scope-analysis.schema.json").read_text()
    )
    return Draft202012Validator(schema)


def validate_test_scope(value: dict, material: dict | None = None) -> None:
    """Check structure, unique identifiers, and references to frozen material when available."""
    errors = list(_validator().iter_errors(value))
    if errors:
        raise ValueError(f"测试范围分析格式错误: {errors[0].message}")
    groups = {
        name: value[name] for name in ("testObjects", "impactAreas", "risks", "openQuestions")
    }
    ids = {}
    for name, entries in groups.items():
        values = [item["id"] for item in entries]
        if len(values) != len(set(values)):
            raise ValueError(f"{name} 标识重复")
        ids[name] = set(values)
    blocks = {item["id"] for item in material.get("materialBlocks", [])} if material else None
    questions = {item["id"] for item in material.get("questions", [])} if material else None
    for entries in groups.values():
        for item in entries:
            for key, target in (
                ("testObjectIds", ids["testObjects"]),
                ("impactAreaIds", ids["impactAreas"]),
                ("riskIds", ids["risks"]),
                ("sourceBlockIds", blocks),
                ("sourceQuestionIds", questions),
            ):
                if target is not None and not set(item.get(key, [])) <= target:
                    raise ValueError(f"{item['id']} 的 {key} 引用了不存在的标识")


def parse_test_scope(content: str) -> dict:
    """Parse a current analysis artifact before using it as downstream input."""
    try:
        value = json.loads(content)
        if not isinstance(value, dict):
            raise ValueError("测试范围风险分析必须是 JSON 对象")
        validate_test_scope(value)
        return value
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("测试范围风险分析格式不受支持，请重新生成并审核") from exc
