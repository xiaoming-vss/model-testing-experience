"""API case generation agent chain."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from testing_agent_ai_worker.agent.prompt import (
    API_EXTRACTOR_JSON_ONLY_INSTRUCTION,
    API_GENERATOR_YAML_ONLY_INSTRUCTION,
    append_stage_instruction,
    build_skill_message,
)
from testing_agent_ai_worker.tasks.api_case_generate.contracts import (
    validate_cases,
    validate_extraction,
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
    """为 OpenAPI 配置提取阶段追加专用 JSON-only 输出约束。"""

    return append_stage_instruction(extra_instruction, API_EXTRACTOR_JSON_ONLY_INSTRUCTION)


def _build_api_generator_instruction(extra_instruction: str) -> str:
    """为 API 用例 YAML 生成阶段追加专用 YAML-only 输出约束。"""

    return append_stage_instruction(extra_instruction, API_GENERATOR_YAML_ONLY_INSTRUCTION)


async def run_chain(
    *,
    openapi_text: str,
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
            stage="openapi_extract",
            inputs=build_skill_message(
                skill_name=extractor_skill_name,
                body_text=openapi_text,
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
                extra_instruction=_build_api_generator_instruction(extra_instruction),
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
    """Execute and validate one API skill without advancing the other stage."""
    if stage == "openapi_extract":
        skill = "openapi-test-config-extractor"
        instruction = _build_api_extractor_instruction(extra_instruction)
        validate = validate_extraction
    elif stage == "generate":
        skill = "api-cases-yaml-generator"
        instruction = _build_api_generator_instruction(extra_instruction)
        validate = validate_cases
    else:
        raise ValueError("不支持的 API 生成阶段")
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
