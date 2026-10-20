"""AI execution formats and stage layout, independent of persistence."""

import json
from collections.abc import Sequence
from copy import deepcopy
from typing import Any, Protocol


class StageLike(Protocol):
    @property
    def stage(self) -> str: ...


FIELDS = {
    "requirement_analysis": "requirementAnalysis",
    "case_names": "caseNames",
    "extracting_text": "firstStepOutput",
    "relation_analysis": "caseRelations",
}


TERMINAL = {"success", "failed", "error", "canceled"}


NO_REVIEW_STAGES = {"relation_analysis"}


NO_REVIEW_KINDS = {"test_order_graph"}


def mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return deepcopy(value) if isinstance(value, dict) else {}


def content(value: Any) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def extra_config(config: Any) -> dict[str, Any]:
    return {
        k: deepcopy(v)
        for k, v in mapping(config).items()
        if k not in {*FIELDS.values(), "revisionInstruction", "resultYaml"}
    }


def output_format(value: str | None) -> str:
    if value is None:
        return "text"
    try:
        json.loads(value)
        return "json"
    except (ValueError, TypeError):
        return "text"


def layout(kind: str) -> list[str]:
    if kind == "functional_case_generate":
        return [
            "requirement_analysis",
            "case_names",
            "detailed_cases",
            "relation_analysis",
        ]
    if kind == "requirement_analysis":
        return ["extracting_text", "feature_understanding"]
    return ["generate"]


def final_stage[T: StageLike](stages: Sequence[T]) -> T:
    """detailed_cases 携带 resultYaml 与运行级审核；relation_analysis 只是派生产物。"""

    for stage in stages:
        if stage.stage == "detailed_cases":
            return stage
    return stages[-1]


def final_review_stage(kind: str, names: Sequence[str]) -> str:
    """非 checkpoint 运行只有最终产物阶段承接运行级审核。"""

    return "detailed_cases" if kind == "functional_case_generate" else names[-1]
