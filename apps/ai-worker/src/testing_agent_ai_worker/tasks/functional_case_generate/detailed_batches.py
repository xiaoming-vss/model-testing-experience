"""Functional detailed case batching helpers."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any
from uuid import uuid4

from testing_agent_ai_worker.agent.prompt import (
    FUNCTIONAL_DETAILED_CASES_JSON_ONLY_INSTRUCTION,
    append_stage_instruction,
    build_skill_message,
)
from testing_agent_ai_worker.traceable_test_points import validate_traceable_test_points

from .case_ids import assign_case_ids
from .module_execution import ModuleProgress, prepare_module_workspace
from .validation import context, generate_validated, normalize_json

LOGGER = logging.getLogger("testing_agent_ai_worker")


def _default_from_config(**kwargs: Any) -> Any:
    """延迟导入 agent，避免单元测试在无 SDK 环境下提前失败。"""

    from testing_agent_ai_worker.agent import create_agent

    return create_agent(**kwargs)


def _build_functional_detailed_case_body(
    *,
    requirement_analysis_json: str,
    case_names_json: str,
    source_text: str = "",
) -> str:
    """为 detailed cases skill 构造固定输入骨架。"""

    return "\n\n".join(
        [
            "【需求材料】",
            source_text.strip(),
            "【需求分析/测试点 JSON】",
            requirement_analysis_json.strip(),
            "【测试用例名称 JSON】",
            case_names_json.strip(),
        ]
    )


def _build_functional_detailed_case_instruction(extra_instruction: str) -> str:
    """为 detailed cases 追加 JSON-only 约束。"""

    return append_stage_instruction(
        extra_instruction, FUNCTIONAL_DETAILED_CASES_JSON_ONLY_INSTRUCTION
    )


def _normalize_json_text(raw_json_text: str) -> str:
    """移除模型可能返回的 markdown fence，保留纯 JSON 文本。"""

    return normalize_json(raw_json_text)


def _build_model_batches(case_names_json: str) -> list[dict[str, Any]]:
    """按功能项拆分，保留测试点及其来源、覆盖缺口和相关审查问题。"""
    artifact = json.loads(_normalize_json_text(case_names_json))
    validate_traceable_test_points(artifact)
    groups: dict[str, list[dict[str, Any]]] = {}
    for point in artifact["testPoints"]:
        groups.setdefault(point["module"], []).append(point)
    if not groups:
        groups["空测试点分组"] = []
    batches = []
    for module, points in groups.items():
        point_ids = {point["id"] for point in points}
        payload = {**artifact, "testPoints": points}
        if "reviewIssues" in payload:
            payload["reviewIssues"] = [
                issue
                for issue in payload["reviewIssues"]
                if issue["targetType"] != "testPoint" or issue["targetId"] in point_ids
            ]
        batches.append({"model_name": module, "payload": payload})
    return batches


def _extract_cases(raw_result: str, model_name: str) -> list[Any]:
    """从单个 detailed cases 分片结果中提取 `cases` 数组。"""

    parsed_result = json.loads(_normalize_json_text(raw_result))
    if not isinstance(parsed_result, dict):
        raise ValueError(f"详细测试用例分片结果顶层必须是对象: model={model_name}")

    cases = parsed_result.get("cases")
    if not isinstance(cases, list):
        raise ValueError(f"详细测试用例分片结果 cases 必须是数组: model={model_name}")
    return cases


async def _run_detailed_case_phase(bot, prompt: str, *, session_key: str, media_args: dict) -> Any:
    """Run one program-dispatched agent without recursive model delegation."""
    started = time.monotonic()
    usage: dict = {}
    status = "failed"
    try:
        result = await bot.run(prompt, session_key=session_key, **media_args)
        usage = getattr(result, "usage", {}) or {}
        status = "completed"
        return result
    finally:
        execution = context.get()
        LOGGER.info(
            "detailed_cases_call task_id=%s run_id=%s status=%s elapsed_ms=%d subagents=%s subagent_input=%s subagent_output=%s",
            execution.task_id if execution else "",
            execution.run_id if execution else "",
            status,
            round((time.monotonic() - started) * 1000),
            usage.get("subagent_count", 0),
            usage.get("subagent_input", 0),
            usage.get("subagent_output", 0),
        )


async def run_functional_detailed_case_batches(
    *,
    requirement_analysis_json: str,
    case_names_json: str,
    session_key: str,
    skill_name: str,
    config_path: str | None = None,
    workspace: str | None = None,
    extra_instruction: str = "",
    on_progress: Callable[[str, str, int, int], None] | None = None,
    from_config: Callable[..., Any] | None = None,
    current_cases_json: str = "",
    revision_instruction: str = "",
    source_text: str = "",
    media: list[str] | None = None,
) -> str:
    """执行 detailed cases 的分片生成并合并结果。"""

    factory = from_config or _default_from_config
    merged_cases: list[Any] = []
    batches = _build_model_batches(case_names_json)
    current_cases = []
    if current_cases_json.strip() and revision_instruction:
        current_cases = _extract_cases(current_cases_json, "当前候选结果")
        # Edited candidates may contain modules absent from the original test points.
        known_modules = {batch["model_name"] for batch in batches}
        for case in current_cases:
            module = (
                str(case.get("case_module") or case.get("module") or "未分组").strip() or "未分组"
            )
            if module not in known_modules:
                batches.append(
                    {
                        "model_name": module,
                        "payload": {
                            **batches[0]["payload"],
                            "testPoints": [],
                            "reviewIssues": [
                                issue
                                for issue in batches[0]["payload"].get("reviewIssues", [])
                                if issue["targetType"] != "testPoint"
                            ],
                        },
                    }
                )
                known_modules.add(module)

    prompts: list[str] = []
    for batch in batches:
        body = _build_functional_detailed_case_body(
            source_text=source_text,
            requirement_analysis_json=requirement_analysis_json,
            case_names_json=json.dumps(batch["payload"], ensure_ascii=False),
        )
        if revision_instruction:
            module_cases = [
                case
                for case in current_cases
                if (
                    str(case.get("case_module") or case.get("module") or "未分组").strip()
                    or "未分组"
                )
                == batch["model_name"]
            ]
            body += (
                "\n\n【当前模块候选用例】\n"
                + json.dumps({"cases": module_cases}, ensure_ascii=False)
                + "\n\n【本轮优化要求】\n"
                + revision_instruction
                + "\n请保留未涉及修改的用例，输出当前模块优化后的完整用例集合。"
            )
        prompts.append(
            build_skill_message(
                skill_name=skill_name,
                body_text=body,
                extra_instruction=_build_functional_detailed_case_instruction(extra_instruction)
                + "\n本次是程序分派的独立模块任务，只处理本模块，不再委派子任务。",
            )
        )

    execution = context.get()
    progress = ModuleProgress([batch["model_name"] for batch in batches], execution)
    slots = asyncio.Semaphore(2)
    dispatch = uuid4().hex
    workspaces: dict[int, str | None] = {}
    stopping = False

    async def run_module(index: int, *, initial: str | None = None) -> str:
        nonlocal stopping
        batch = batches[index]
        async with slots:
            if stopping:
                raise asyncio.CancelledError()
            token = None
            try:
                await progress.emit(index, "running" if initial is None else "repairing")
                if index not in workspaces:
                    workspaces[index] = await asyncio.to_thread(
                        prepare_module_workspace, workspace, dispatch, index
                    )

                async def report_validation(event: dict) -> None:
                    if event.get("status") == "repairing":
                        await progress.emit(
                            index, "repairing", repairAttempt=event["repairAttempt"]
                        )

                if execution:
                    token = context.set(replace(execution, report=report_validation))
                async with factory(config_path=config_path, workspace=workspaces[index]) as bot:
                    result = await generate_validated(
                        stage="detailed_cases",
                        module=batch["model_name"],
                        batch=index + 1,
                        previous_cases=merged_cases if initial is not None else (),
                        initial_response=initial,
                        generate=lambda prompt: _run_detailed_case_phase(
                            bot,
                            prompt,
                            session_key=f"{session_key}:module:{dispatch}:{index}",
                            media_args={"media": media} if media else {},
                        ),
                        inputs=prompts[index],
                    )
                await progress.emit(
                    index, "completed", caseCount=len(_extract_cases(result, batch["model_name"]))
                )
                return result
            except asyncio.CancelledError:
                raise
            except Exception:
                stopping = True
                await progress.emit(index, "failed")
                raise
            finally:
                if token is not None:
                    context.reset(token)

    await progress.emit()
    tasks = [asyncio.create_task(run_module(index)) for index in range(len(batches))]
    try:
        outputs = await asyncio.gather(*tasks)
        await progress.emit(status="merging")
        for index, output in enumerate(outputs):
            # Cross-module validation remains ordered and retains bounded repair.
            from .validation import validate_output

            try:
                validate_output("detailed_cases", output, previous_cases=merged_cases)
            except (ValueError, TypeError):
                output = await run_module(index, initial=output)
            merged_cases.extend(_extract_cases(output, batches[index]["model_name"]))
            if on_progress is not None:
                await asyncio.to_thread(
                    on_progress, "", batches[index]["model_name"], index + 1, len(batches)
                )
        result = json.dumps(
            {"cases": assign_case_ids(merged_cases, current_cases)}, ensure_ascii=False
        )
        await progress.emit(status="completed")
        return result
    except BaseException as error:
        stopping = True
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await progress.stop("canceled" if isinstance(error, asyncio.CancelledError) else "failed")
        raise
