"""Functional test case generation agent chain."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from testing_agent_ai_worker.agent.prompt import (
    FUNCTIONAL_ANALYSIS_JSON_ONLY_INSTRUCTION,
    FUNCTIONAL_CASE_NAMES_JSON_ONLY_INSTRUCTION,
    FUNCTIONAL_RELATION_JSON_ONLY_INSTRUCTION,
    append_stage_instruction,
    build_skill_message,
)
from testing_agent_ai_worker.skill_names import CASE_RELATIONS_SKILL, SCOPE_SKILL, TEST_POINTS_SKILL
from testing_agent_ai_worker.tasks.functional_case_generate.detailed_batches import (
    run_functional_detailed_case_batches,
)

from .module_execution import prepare_module_workspace
from .traceable_review import generate_traceable_points
from .validation import generate_validated, validate_output


def _default_from_config(**kwargs: Any) -> Any:
    """延迟导入 agent，避免单元测试在无 SDK 环境下提前失败。"""

    from testing_agent_ai_worker.agent import create_agent

    return create_agent(**kwargs)


@dataclass(slots=True)
class FunctionalChainRunResult:
    requirement_analysis_output: str
    case_names_output: str
    detailed_cases_output: str


def _analysis_material(text: str) -> dict[str, Any] | None:
    """Extract material from the beginning of a stage input, before revision text."""
    try:
        value, _ = json.JSONDecoder().raw_decode(text.lstrip())
    except (ValueError, TypeError):
        return None
    if isinstance(value, dict) and value.get("artifactType") == "readable_requirement_material":
        return value
    return None


def _build_functional_analysis_instruction(extra_instruction: str) -> str:
    """构造测试范围风险分析阶段输出约束。"""

    return append_stage_instruction(extra_instruction, FUNCTIONAL_ANALYSIS_JSON_ONLY_INSTRUCTION)


def _traceable_inputs(text: str) -> tuple[dict, dict]:
    """Read the frozen JSON values before any optional revision instructions."""
    decoder = json.JSONDecoder()
    material_text = text.split("【需求材料】", 1)[1].lstrip()
    material, end = decoder.raw_decode(material_text)
    tail = material_text[end:].lstrip()
    marker = "【需求分析结果 JSON】"
    if not tail.startswith(marker):
        raise ValueError("测试点缺少冻结的测试范围分析")
    scope, _ = decoder.raw_decode(tail[len(marker) :].lstrip())
    if not isinstance(material, dict) or not isinstance(scope, dict):
        raise ValueError("测试点缺少材料整理或测试范围分析")
    return material, scope


def _build_functional_case_names_body(*, source_text: str, analysis_json: str) -> str:
    """测试点生成同时接收已审核材料及结构化分析，支持独立阶段恢复。"""

    return "\n\n".join(
        [
            "【需求材料】",
            source_text.strip(),
            "【需求分析结果 JSON】",
            analysis_json.strip(),
            "【输入版本】以上两份产物由平台在当前任务中配套冻结，测试范围分析基于该材料版本。",
        ]
    )


def _build_functional_case_names_instruction(extra_instruction: str) -> str:
    """构造测试点阶段输出约束。"""

    return append_stage_instruction(extra_instruction, FUNCTIONAL_CASE_NAMES_JSON_ONLY_INSTRUCTION)


def _build_functional_relation_instruction(extra_instruction: str) -> str:
    """构造用例关联分析阶段输出约束。"""

    return append_stage_instruction(extra_instruction, FUNCTIONAL_RELATION_JSON_ONLY_INSTRUCTION)


def _build_functional_relation_body(
    *,
    material_json: str,
    cases_json: str,
) -> str:
    """用冻结的材料整理结果和完整用例构造图谱输入。"""

    return (
        f"【材料整理结果 JSON】\n\n{material_json.strip()}"
        f"\n\n【完整测试用例 JSON】\n\n{cases_json.strip()}"
    )


def _build_functional_instruction_for_skill(skill_name: str, extra_instruction: str) -> str:
    """按功能链路 skill 名称追加对应输出约束。"""

    if skill_name == SCOPE_SKILL:
        return _build_functional_analysis_instruction(extra_instruction)
    if skill_name == TEST_POINTS_SKILL:
        return _build_functional_case_names_instruction(extra_instruction)
    if skill_name == CASE_RELATIONS_SKILL:
        return _build_functional_relation_instruction(extra_instruction)
    return extra_instruction


async def _run_traceable_phase(
    *, factory, bot, config_path, workspace, session_key, prompt, phase, media_args
):
    phase_session = session_key if phase == "generate" else f"{session_key}:{phase}"
    if phase.startswith("draft-"):
        _, dispatch, index = phase.split("-")
        child_workspace = await asyncio.to_thread(
            prepare_module_workspace, workspace, f"points-{dispatch}", int(index)
        )
        async with factory(config_path=config_path, workspace=child_workspace) as child:
            return await child.run(prompt, session_key=phase_session, **media_args)
    if phase.startswith("audit-"):
        # Agent contexts serialize their own calls; separate contexts permit independent reviews.
        async with factory(config_path=config_path, workspace=workspace) as reviewer:
            delegated_run = getattr(reviewer, "run_with_subagents", None)
            if callable(delegated_run):
                if media_args:
                    prompt += "\n\n子 Agent 不接收图片；请由主 Agent 直接核对图片信息。"
                return await delegated_run(
                    prompt,
                    session_key=phase_session,
                    delegation_kind="test_point_review",
                    **media_args,
                )
            return await reviewer.run(prompt, session_key=phase_session, **media_args)
    delegated_run = getattr(bot, "run_with_subagents", None)
    if phase == "generate" and callable(delegated_run):
        if media_args:
            prompt += "\n\n子 Agent 不接收图片；请由主 Agent 直接核对图片信息。"
        return await delegated_run(prompt, session_key=phase_session, **media_args)
    return await bot.run(prompt, session_key=phase_session, **media_args)


async def run_skill_step(
    *,
    input_text: str,
    session_key: str,
    skill_name: str,
    config_path: str | None = None,
    workspace: str | None = None,
    extra_instruction: str = "",
    expected_case_ids: list[str] | None = None,
    is_revision: bool = False,
    media: list[str] | None = None,
    from_config: Callable[..., Any] | None = None,
) -> str:
    """执行单步 skill。"""

    factory = from_config or _default_from_config

    message = build_skill_message(
        skill_name=skill_name,
        body_text=input_text,
        extra_instruction=_build_functional_instruction_for_skill(skill_name, extra_instruction),
    )
    media_args = {"media": media} if media else {}
    async with factory(config_path=config_path, workspace=workspace) as bot:
        stage = {
            SCOPE_SKILL: "requirement_analysis",
            TEST_POINTS_SKILL: "case_names",
            CASE_RELATIONS_SKILL: "relation_analysis",
        }.get(skill_name)
        if stage is None:
            return (await bot.run(message, session_key=session_key, **media_args)).content
        if stage == "case_names":
            material, scope = _traceable_inputs(input_text)
            if not workspace:
                raise ValueError("测试点生成缺少工作目录")
            return await generate_traceable_points(
                generation_input=message,
                parallel_draft=not is_revision,
                skill_name=skill_name,
                material=material,
                scope=scope,
                workspace=workspace,
                autonomous_review=callable(getattr(bot, "run_with_subagents", None)),
                generate=lambda prompt, phase: _run_traceable_phase(
                    factory=factory,
                    bot=bot,
                    config_path=config_path,
                    workspace=workspace,
                    session_key=session_key,
                    prompt=prompt,
                    phase=phase,
                    media_args=media_args,
                ),
            )
        return await generate_validated(
            stage=stage,
            inputs=message,
            material=_analysis_material(input_text) if stage == "requirement_analysis" else None,
            generate=lambda prompt: bot.run(prompt, session_key=session_key, **media_args),
            expected_case_ids=expected_case_ids,
        )


async def run_functional_chain(
    *,
    source_text: str,
    session_key: str,
    analysis_skill_name: str,
    case_name_skill_name: str,
    detailed_case_skill_name: str,
    config_path: str | None = None,
    workspace: str | None = None,
    extra_instruction: str = "",
    on_requirement_analysis_result: Callable[[str], None] | None = None,
    on_case_names_result: Callable[[str], None] | None = None,
    on_detailed_cases_progress: Callable[[str, str, int, int], None] | None = None,
    resume_stage: str = "",
    prior_analysis: str = "",
    prior_case_names: str = "",
    from_config: Callable[..., Any] | None = None,
) -> FunctionalChainRunResult:
    """执行功能测试用例生成的完整三段链路。"""

    factory = from_config or _default_from_config

    async with factory(config_path=config_path, workspace=workspace) as bot:
        if resume_stage in {"case_names", "detailed_cases"}:
            if not prior_analysis.strip():
                raise ValueError("阶段重试缺少已确认需求分析")
            validate_output("requirement_analysis", prior_analysis)
            analysis_result = prior_analysis
        else:
            analysis_result = await generate_validated(
                stage="requirement_analysis",
                material=_analysis_material(source_text),
                generate=lambda prompt: bot.run(prompt, session_key=session_key),
                inputs=build_skill_message(
                    skill_name=analysis_skill_name,
                    body_text=source_text,
                    extra_instruction=_build_functional_analysis_instruction(extra_instruction),
                ),
            )
        if on_requirement_analysis_result is not None and resume_stage not in {
            "case_names",
            "detailed_cases",
        }:
            on_requirement_analysis_result(analysis_result)

        if resume_stage == "detailed_cases":
            if not prior_case_names.strip():
                raise ValueError("阶段重试缺少已确认测试点")
            case_names_result = prior_case_names
        else:
            case_names_body = _build_functional_case_names_body(
                source_text=source_text,
                analysis_json=analysis_result,
            )
            if not workspace:
                raise ValueError("测试点生成缺少工作目录")
            material, scope = _traceable_inputs(case_names_body)
            case_names_result = await generate_traceable_points(
                generation_input=build_skill_message(
                    skill_name=case_name_skill_name,
                    body_text=case_names_body,
                    extra_instruction=_build_functional_case_names_instruction(extra_instruction),
                ),
                parallel_draft=True,
                material=material,
                scope=scope,
                workspace=workspace,
                skill_name=case_name_skill_name,
                autonomous_review=callable(getattr(bot, "run_with_subagents", None)),
                generate=lambda prompt, phase: _run_traceable_phase(
                    factory=factory,
                    bot=bot,
                    config_path=config_path,
                    workspace=workspace,
                    session_key=session_key,
                    prompt=prompt,
                    phase=phase,
                    media_args={},
                ),
            )
        if on_case_names_result is not None and resume_stage != "detailed_cases":
            on_case_names_result(case_names_result)

        detailed_cases_result = await run_functional_detailed_case_batches(
            source_text=source_text,
            requirement_analysis_json=analysis_result,
            case_names_json=case_names_result,
            session_key=session_key,
            skill_name=detailed_case_skill_name,
            config_path=config_path,
            workspace=workspace,
            extra_instruction=extra_instruction,
            on_progress=on_detailed_cases_progress,
            from_config=factory,
        )

    return FunctionalChainRunResult(
        requirement_analysis_output=analysis_result,
        case_names_output=case_names_result,
        detailed_cases_output=detailed_cases_result,
    )
