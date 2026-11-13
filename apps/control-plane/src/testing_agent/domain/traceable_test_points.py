"""Validate traceable test points against their frozen upstream artifacts."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    path = Path(__file__).parent / "requirement_schemas/traceable-test-points.schema.json"
    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))


def validate_traceable_test_points(
    value: dict[str, Any],
    material: dict[str, Any] | None = None,
    analysis: dict[str, Any] | None = None,
) -> None:
    """Check schema, point identity, names and references when upstreams are available."""
    errors = list(_validator().iter_errors(value))
    if errors:
        raise ValueError(f"测试点格式错误: {errors[0].message}")
    for group in ("testPoints", "coverageGaps"):
        ids = [entry["id"] for entry in value[group]]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{group} 标识重复")
    for point in value["testPoints"]:
        prefix = f"【{point['module']}】"
        if not any(point["name"].startswith(prefix + verb) for verb in ("验证", "测量", "观察")):
            raise ValueError(f"{point['id']} 名称与功能项不一致")
        if point["name"].startswith((prefix + "测量", prefix + "观察")) and point[
            "dimension"
        ] not in ("性能场景", "长稳场景"):
            raise ValueError(f"{point['id']} 测量场景无效")
    issues = value.get("reviewIssues", [])
    if value["reviewStatus"] == "independent_reviewed" and issues:
        raise ValueError("独立审查通过的产物不能包含未解决问题")
    point_ids = {entry["id"] for entry in value["testPoints"]}
    gap_ids = {entry["id"] for entry in value["coverageGaps"]}
    for issue in issues:
        target_type = issue["targetType"]
        target = issue["targetId"]
        if target_type == "missing":
            if target is not None or issue["kind"] != "missing":
                raise ValueError("审查遗漏问题目标无效")
        elif target not in (point_ids if target_type == "testPoint" else gap_ids):
            raise ValueError("审查问题引用了不存在的目标")
    targets = {
        "materialBlockIds": (material, "materialBlocks"),
        "materialQuestionIds": (material, "questions"),
        "testObjectIds": (analysis, "testObjects"),
        "impactAreaIds": (analysis, "impactAreas"),
        "riskIds": (analysis, "risks"),
        "scopeQuestionIds": (analysis, "openQuestions"),
    }
    for group in ("testPoints", "coverageGaps", "reviewIssues"):
        for entry in value.get(group, []):
            for field, (source, collection) in targets.items():
                if source is not None:
                    valid = {item["id"] for item in source.get(collection, [])}
                    if not set(entry[field]) <= valid:
                        entry_id = entry.get("id") or entry.get("targetId")
                        raise ValueError(f"{entry_id} 的 {field} 引用了不存在的标识")
