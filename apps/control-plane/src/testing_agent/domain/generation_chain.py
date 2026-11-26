"""Requirement generation chain vocabulary and stage dependency rules.

Stage definitions are shared by legacy chains and candidate chains. Candidate
chains use one adopted current result per stage, with explicit trial sources.
"""

from __future__ import annotations

import json
from typing import Any

CHAIN_KINDS = ("requirement_analysis", "function", "api", "ui")
HISTORICAL_REQUIREMENT_STAGE = "historical_requirement_relations"
HISTORICAL_TEST_STAGE = "historical_test_case_verification"
HISTORICAL_STAGES = {HISTORICAL_REQUIREMENT_STAGE, HISTORICAL_TEST_STAGE}
CANDIDATE_DELETED_REASON = "审核未通过，候选产物已删除"

CHAIN_LABELS = {
    "requirement_analysis": "需求分析",
    "function": "功能测试",
    "api": "API 测试",
    "ui": "UI 测试",
}

STAGE_DEFINITIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "requirement_analysis": (
        ("requirement_review", "需求评审"),
        ("extracting_text", "材料整理"),
        (HISTORICAL_REQUIREMENT_STAGE, "历史需求关联"),
        (HISTORICAL_TEST_STAGE, "历史用例核验"),
    ),
    "function": (
        ("requirement_analysis", "测试范围风险分析"),
        ("case_names", "测试点"),
        ("detailed_cases", "完整用例"),
    ),
    "api": (
        ("interface_extract", "接口配置提取"),
        ("api_design", "接口用例设计"),
        ("generate", "API 用例生成"),
    ),
    "ui": (
        ("ui_surface", "元素控件清单"),
        ("ui_design", "UI 用例设计"),
        ("ui_yaml", "用例 YAML"),
    ),
}

# The profile has an independent current slot; it is not one of the canvas chains.
AUXILIARY_STAGE_DEFINITIONS = {"repository_profile": (("generate", "仓库画像"),)}

# Functional generation consumes the current adopted material content.
STAGE_UPSTREAMS: dict[str, tuple[str, ...]] = {
    # The review report is advisory: extraction is independent of it.
    "requirement_review": (),
    "extracting_text": (),
    HISTORICAL_REQUIREMENT_STAGE: ("extracting_text",),
    HISTORICAL_TEST_STAGE: (HISTORICAL_REQUIREMENT_STAGE,),
    "requirement_analysis": ("extracting_text",),
    "case_names": ("requirement_analysis",),
    "detailed_cases": ("requirement_analysis", "case_names"),
    "ui_surface": (),
    "ui_design": ("ui_surface",),
    "ui_yaml": ("ui_surface", "ui_design"),
    "interface_extract": (),
    "api_design": ("interface_extract",),
    "generate": ("interface_extract", "api_design"),
}

# JSON artifacts are stored as a single config field; final artifacts use resultYaml.
STAGE_CONFIG_FIELDS = {
    "requirement_review": "reviewOutput",
    "extracting_text": "firstStepOutput",
    HISTORICAL_REQUIREMENT_STAGE: "historicalRequirementRelations",
    HISTORICAL_TEST_STAGE: "historicalTestCaseVerification",
    "requirement_analysis": "requirementAnalysis",
    "case_names": "caseNames",
    "ui_surface": "uiSurface",
    "ui_design": "uiDesign",
    "detailed_cases": "resultYaml",
    "ui_yaml": "resultYaml",
    "interface_extract": "apiExtraction",
    "api_design": "apiDesign",
    "generate": "resultYaml",
}

JSON_ARTIFACT_STAGES = {
    "requirement_review",
    "extracting_text",
    HISTORICAL_REQUIREMENT_STAGE,
    HISTORICAL_TEST_STAGE,
    "interface_extract",
    "api_design",
    "requirement_analysis",
    "case_names",
    "ui_surface",
    "ui_design",
}


def stage_names(kind: str) -> tuple[str, ...]:
    definitions = STAGE_DEFINITIONS if kind in STAGE_DEFINITIONS else AUXILIARY_STAGE_DEFINITIONS
    return tuple(stage for stage, _ in definitions[kind])


def stage_label(kind: str, stage: str) -> str:
    definitions = STAGE_DEFINITIONS if kind in STAGE_DEFINITIONS else AUXILIARY_STAGE_DEFINITIONS
    return dict(definitions[kind]).get(
        stage, dict(STAGE_DEFINITIONS.get(kind_for_stage(stage), ())).get(stage, stage)
    )


def kind_for_stage(stage: str) -> str:
    """Return the chain kind owning a stage; unknown stages return an empty string."""
    for kind, definitions in STAGE_DEFINITIONS.items():
        if any(name == stage for name, _ in definitions):
            return kind
    return ""


def is_final_stage(kind: str, stage: str) -> bool:
    if kind == "requirement_analysis":
        return stage == "extracting_text" or stage in HISTORICAL_STAGES
    return stage == stage_names(kind)[-1]


def upstream_stages(kind: str, stage: str) -> tuple[str, ...]:
    return STAGE_UPSTREAMS.get(stage, ())


def artifact_is_json(stage: str, artifact_format: str | None = None) -> bool:
    if artifact_format:
        return artifact_format == "json"
    return stage in JSON_ARTIFACT_STAGES


def artifact_value(stage: str, content: str, artifact_format: str | None = None) -> Any:
    if artifact_is_json(stage, artifact_format):
        try:
            return json.loads(content)
        except (TypeError, ValueError):
            return content
    return content
