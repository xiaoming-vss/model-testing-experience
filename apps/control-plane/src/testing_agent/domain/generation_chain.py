"""Requirement generation chain vocabulary and stage dependency rules.

A chain is one AI task per requirement and kind. A stage version is approved
content; downstream stages read the latest approved version unless the operator
explicitly selects an older one when starting a draft.
"""

from __future__ import annotations

import json
from typing import Any

CHAIN_KINDS = ("requirement_analysis", "function", "api", "ui")

CHAIN_LABELS = {
    "requirement_analysis": "需求分析",
    "function": "功能测试",
    "api": "API 测试",
    "ui": "UI 测试",
}

STAGE_DEFINITIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "requirement_analysis": (("extracting_text", "材料整理"),),
    "function": (
        ("requirement_analysis", "测试范围风险分析"),
        ("case_names", "测试点"),
        ("detailed_cases", "完整用例"),
    ),
    "api": (("openapi_extract", "接口配置提取"), ("generate", "API 用例生成")),
    "ui": (
        ("ui_surface", "元素控件清单"),
        ("ui_design", "UI 用例设计"),
        ("ui_yaml", "用例 YAML"),
    ),
}

# Functional generation consumes the approved material version.
STAGE_UPSTREAMS: dict[str, tuple[str, ...]] = {
    "extracting_text": (),
    "requirement_analysis": ("extracting_text",),
    "case_names": ("requirement_analysis",),
    "detailed_cases": ("requirement_analysis", "case_names"),
    "ui_surface": (),
    "ui_design": ("ui_surface",),
    "ui_yaml": ("ui_surface", "ui_design"),
    "openapi_extract": (),
    "generate": ("openapi_extract",),
}

# JSON artifacts are stored as a single config field; final artifacts use resultYaml.
STAGE_CONFIG_FIELDS = {
    "extracting_text": "firstStepOutput",
    "requirement_analysis": "requirementAnalysis",
    "case_names": "caseNames",
    "ui_surface": "uiSurface",
    "ui_design": "uiDesign",
    "detailed_cases": "resultYaml",
    "ui_yaml": "resultYaml",
    "openapi_extract": "apiExtraction",
    "generate": "resultYaml",
}

JSON_ARTIFACT_STAGES = {
    "extracting_text",
    "openapi_extract",
    "requirement_analysis",
    "case_names",
    "ui_surface",
    "ui_design",
}


def stage_names(kind: str) -> tuple[str, ...]:
    return tuple(stage for stage, _ in STAGE_DEFINITIONS[kind])


def stage_label(kind: str, stage: str) -> str:
    return dict(STAGE_DEFINITIONS[kind]).get(
        stage, dict(STAGE_DEFINITIONS.get(kind_for_stage(stage), ())).get(stage, stage)
    )


def kind_for_stage(stage: str) -> str:
    """Return the chain kind owning a stage; unknown stages return an empty string."""
    for kind, definitions in STAGE_DEFINITIONS.items():
        if any(name == stage for name, _ in definitions):
            return kind
    return ""


def is_final_stage(kind: str, stage: str) -> bool:
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


def artifact_summary(stage: str, content: str, artifact_format: str | None = None) -> str:
    """Short, stable copy for map nodes; never parse unbounded user text."""
    if not content:
        return "暂无产物"
    if artifact_is_json(stage, artifact_format):
        try:
            data = json.loads(content)
        except (TypeError, ValueError):
            return f"{len(content)} 字符"
        if isinstance(data, dict):
            for key, unit in (
                ("testPoints", "个测试点"),
                ("cases", "条用例"),
                ("pages", "个页面"),
                ("modules", "个模块"),
                ("businessFlows", "条流程"),
                ("controls", "个控件"),
                ("categories", "个分类"),
            ):
                value = data.get(key)
                if isinstance(value, list):
                    return f"{len(value)} {unit}"
            return f"{len(data)} 个字段"
        if isinstance(data, list):
            return f"{len(data)} 项"
        return "1 项内容"
    stripped = content.strip()
    if not stripped:
        return "暂无产物"
    if stripped.startswith("- "):
        return f"{sum(1 for line in stripped.splitlines() if line.startswith('- '))} 条记录"
    return f"{len(stripped)} 字符"
