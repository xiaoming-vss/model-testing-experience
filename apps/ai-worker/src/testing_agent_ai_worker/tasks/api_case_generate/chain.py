"""API case generation agent chain."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from testing_agent_ai_worker.agent.prompt import (
    API_DESIGNER_JSON_ONLY_INSTRUCTION,
    API_EXTRACTOR_JSON_ONLY_INSTRUCTION,
    API_GENERATOR_LEGACY_YAML_ONLY_INSTRUCTION,
    API_GENERATOR_YAML_ONLY_INSTRUCTION,
    append_stage_instruction,
    build_skill_message,
)
from testing_agent_ai_worker.core.errors import UserFacingError
from testing_agent_ai_worker.skill_names import (
    API_DESIGN_SKILL,
    API_EXTRACT_SKILL,
    API_GENERATE_SKILL,
)
from testing_agent_ai_worker.tasks.api_case_generate.contracts import (
    validate_cases,
    validate_extraction,
    validate_extraction_object,
)
from testing_agent_ai_worker.tasks.api_case_generate.design_batches import (
    generate_design_batches,
)
from testing_agent_ai_worker.tasks.api_case_generate.design_contract import (
    canonical_design,
    parse_design_json,
    validate_design_object,
)
from testing_agent_ai_worker.tasks.api_case_generate.generation_batches import (
    generate_cases_batches,
)
from testing_agent_ai_worker.tasks.output_repair import generate_validated


def _default_from_config(**kwargs: Any) -> Any:
    """延迟导入 agent，避免单元测试在无 SDK 环境下提前失败。"""

    from testing_agent_ai_worker.agent import create_agent

    return create_agent(**kwargs)


@dataclass(slots=True)
class ChainRunResult:
    extractor_output: str
    generator_output: str


def _build_api_extractor_instruction(extra_instruction: str) -> str:
    """为接口配置提取阶段追加专用 JSON-only 输出约束。"""

    return append_stage_instruction(extra_instruction, API_EXTRACTOR_JSON_ONLY_INSTRUCTION)


def _build_api_designer_instruction(extra_instruction: str) -> str:
    """为接口用例设计阶段追加专用 JSON-only 输出约束。"""

    return append_stage_instruction(extra_instruction, API_DESIGNER_JSON_ONLY_INSTRUCTION)


def _build_api_generator_instruction(extra_instruction: str, *, design_driven: bool = True) -> str:
    """为 API 用例 YAML 生成阶段追加专用 YAML-only 输出约束。"""

    stage_instruction = (
        API_GENERATOR_YAML_ONLY_INSTRUCTION
        if design_driven
        else API_GENERATOR_LEGACY_YAML_ONLY_INSTRUCTION
    )
    return append_stage_instruction(extra_instruction, stage_instruction)


def _stage_payload(input_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(input_text)
    except (TypeError, ValueError) as exc:
        raise UserFacingError("API 设计/生成阶段输入必须是 JSON 对象") from exc
    if not isinstance(payload, dict):
        raise UserFacingError("API 设计/生成阶段输入必须是 JSON 对象")
    return payload


def _extraction_payload(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("apiExtraction")
    return validate_extraction_object(value)


def _design_payload(payload: dict[str, Any], extraction: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("apiDesign")
    if isinstance(value, str):
        value = parse_design_json(value)
    return validate_design_object(value, extraction)


def _requirement_payload(payload: dict[str, Any]) -> dict[str, Any]:
    requirement = payload.get("requirement")
    return requirement if isinstance(requirement, dict) else {}


async def run_chain(
    *,
    source_text: str,
    session_key: str,
    extractor_skill_name: str,
    generator_skill_name: str,
    config_path: str | None = None,
    workspace: str | None = None,
    extra_instruction: str = "",
    on_extractor_result: Callable[[str], None] | None = None,
    on_validation_progress: Callable[[dict[str, Any], str], None] | None = None,
    from_config: Callable[..., Any] | None = None,
) -> ChainRunResult:
    """执行 API 用例生成的两段 skill 链。"""

    factory = from_config or _default_from_config

    async with factory(config_path=config_path, workspace=workspace) as bot:
        directory = Path(workspace) / "diagnostics" / "api-output" if workspace else None
        extractor_output = await generate_validated(
            stage="interface_extract",
            inputs=build_skill_message(
                skill_name=extractor_skill_name,
                body_text=source_text,
                extra_instruction=_build_api_extractor_instruction(extra_instruction),
            ),
            generate=lambda prompt: bot.run(prompt, session_key=session_key),
            validate=validate_extraction,
            diagnostic_dir=directory,
            report=(lambda event: on_validation_progress(event, ""))
            if on_validation_progress
            else None,
        )
        if on_extractor_result is not None:
            on_extractor_result(extractor_output)
        generator_output = await generate_validated(
            stage="api_case_generating",
            inputs=build_skill_message(
                skill_name=generator_skill_name,
                body_text=extractor_output,
                extra_instruction=_build_api_generator_instruction(
                    extra_instruction, design_driven=False
                ),
            ),
            generate=lambda prompt: bot.run(prompt, session_key=session_key),
            validate=validate_cases,
            diagnostic_dir=directory,
            report=(lambda event: on_validation_progress(event, extractor_output))
            if on_validation_progress
            else None,
        )

    return ChainRunResult(extractor_output=extractor_output, generator_output=generator_output)


async def run_api_stage(
    *,
    stage: str,
    input_text: str,
    session_key: str,
    config_path: str | None = None,
    workspace: str | None = None,
    extra_instruction: str = "",
    on_validation_progress: Callable[[dict[str, Any]], None] | None = None,
    from_config: Callable[..., Any] | None = None,
    media: list[str] | None = None,
) -> str:
    """执行并校验一个 API 阶段；设计与生成阶段按接口/用例分批。"""
    if stage == "api_design":
        payload = _stage_payload(input_text)
        extraction = _extraction_payload(payload)
        current_design = payload.get("currentDesign")
        if isinstance(current_design, str):
            current_design = parse_design_json(current_design)
        if current_design is not None and not isinstance(current_design, dict):
            raise UserFacingError("currentDesign 必须是对象")
        revision_instruction = str(payload.get("revisionInstruction") or "").strip()
        skill = API_DESIGN_SKILL
        instruction = _build_api_designer_instruction(extra_instruction)
        factory = from_config or _default_from_config
        async with factory(config_path=config_path, workspace=workspace) as bot:
            design = await generate_design_batches(
                extraction=extraction,
                requirement=_requirement_payload(payload),
                instruction=instruction,
                user_instruction="",
                current_design=current_design,
                revision_instruction=revision_instruction,
                diagnostic_dir=(
                    Path(workspace) / "diagnostics" / "api-design" if workspace else None
                ),
                report=on_validation_progress or (lambda event: None),
                generate=lambda prompt, batch, rules: bot.run(
                    build_skill_message(
                        skill_name=skill, body_text=prompt, extra_instruction=rules
                    ),
                    session_key=f"{session_key}:api-design:{batch}",
                    **({"media": media} if media else {}),
                ),
            )
        return canonical_design(design)
    if stage == "generate":
        payload = _stage_payload(input_text)
        extraction = _extraction_payload(payload)
        design = _design_payload(payload, extraction)
        revision_instruction = str(payload.get("revisionInstruction") or "").strip()
        current_yaml = str(payload.get("currentYaml") or "")
        skill = API_GENERATE_SKILL
        instruction = _build_api_generator_instruction(extra_instruction)
        factory = from_config or _default_from_config
        async with factory(config_path=config_path, workspace=workspace) as bot:
            return await generate_cases_batches(
                extraction=extraction,
                design=design,
                requirement=_requirement_payload(payload),
                instruction=instruction,
                user_instruction="",
                current_yaml=current_yaml,
                revision_instruction=revision_instruction,
                diagnostic_dir=(
                    Path(workspace) / "diagnostics" / "api-cases" if workspace else None
                ),
                report=on_validation_progress or (lambda event: None),
                generate=lambda prompt, batch, rules: bot.run(
                    build_skill_message(
                        skill_name=skill, body_text=prompt, extra_instruction=rules
                    ),
                    session_key=f"{session_key}:api-generate:{batch}",
                    **({"media": media} if media else {}),
                ),
            )
    if stage == "interface_extract":
        skill = API_EXTRACT_SKILL
        instruction = _build_api_extractor_instruction(extra_instruction)
        validate = validate_extraction
    else:
        raise UserFacingError("不支持的 API 生成阶段")
    factory = from_config or _default_from_config
    async with factory(config_path=config_path, workspace=workspace) as bot:
        return await generate_validated(
            stage=stage,
            inputs=build_skill_message(
                skill_name=skill, body_text=input_text, extra_instruction=instruction
            ),
            generate=lambda prompt: bot.run(
                prompt, session_key=session_key, **({"media": media} if media else {})
            ),
            validate=validate,
            diagnostic_dir=Path(workspace) / "diagnostics" / "api-output" if workspace else None,
            report=on_validation_progress,
        )
