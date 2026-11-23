"""AI execution formats and stage layout, independent of persistence."""

import json
from collections.abc import Sequence
from copy import deepcopy
from typing import Any

FIELDS = {
    "requirement_review": "reviewOutput",
    "requirement_analysis": "requirementAnalysis",
    "case_names": "caseNames",
    "extracting_text": "firstStepOutput",
    "interface_extract": "apiExtraction",
    "api_design": "apiDesign",
    "relation_analysis": "caseRelations",
    "ui_surface": "uiSurface",
    "ui_design": "uiDesign",
}


NO_REVIEW_STAGES = {"relation_analysis"}


# Revision inputs live in the attempt snapshot, never in the effective artifact config.


def mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return deepcopy(value) if isinstance(value, dict) else {}


def layout(kind: str) -> list[str]:
    if kind == "functional_case_generate":
        return [
            "requirement_analysis",
            "case_names",
            "detailed_cases",
            "relation_analysis",
        ]
    if kind == "requirement_analysis":
        return ["requirement_review", "extracting_text"]
    return ["generate"]


def final_review_stage(kind: str, names: Sequence[str]) -> str:
    """非 checkpoint 运行只有最终产物阶段承接运行级审核。"""

    return "detailed_cases" if kind == "functional_case_generate" else names[-1]
