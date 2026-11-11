"""Execute exactly one reviewed UI generation stage per queue dispatch."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from testing_agent_ai_worker.models.execution import TaskProgress, TaskResult, TaskStatus
from testing_agent_ai_worker.models.task import Task
from testing_agent_ai_worker.tasks.output_repair import generate_validated
from testing_agent_ai_worker.tasks.ui_case_generate.artifacts import (
    DEFAULT_CAPABILITIES,
    UI_FIELDS,
    UI_SKILLS,
    UI_STAGES,
    UI_WORKFLOW_VERSION,
    validate_design,
    validate_surface,
)

from .batches import generate_batches
from .design_contract import strict_json
from .yaml_batches import generate_yaml_batches


def read_stage_json(raw: str, output_path: Path) -> Any:
    """Read only the caller-owned path, never a location or success claim from model prose."""
    if output_path.is_symlink() or output_path.resolve() != output_path:
        raise ValueError("阶段产物必须写入约定路径，不能使用符号链接或重定向目录")
    if output_path.exists():
        if not output_path.is_file():
            raise ValueError("约定产物路径不是文件")
        return strict_json(output_path.read_text(encoding="utf-8-sig"))
    text = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n(.*)\n```", text, flags=re.DOTALL)
    parsed = strict_json(fenced.group(1).strip() if fenced else text)
    if isinstance(parsed, dict) and "artifactPath" in parsed:
        raise ValueError("模型未在约定 outputPath 写入阶段产物；不得使用其他路径")
    return parsed


def execute_stage(
    *,
    task: Task,
    started_at: datetime,
    progress_callback: Callable,
    source_root: Path,
    workspace: Path,
    config_path: str,
    skill_runner: Callable,
    validate_yaml: Callable[[str], int],
    yaml_instruction: str = "",
    source_metadata: dict[str, Any] | None = None,
) -> TaskResult | None:
    if not task.checkpoint_enabled:
        raise ValueError("三阶段 UI 生成必须启用人工审核")
    stage = task.current_stage
    if stage not in UI_STAGES:
        raise ValueError("不支持的 UI 生成阶段")
    config = json.loads(task.config_json or "{}")
    if not isinstance(config, dict):
        raise ValueError("configJson 必须是对象")
    cases = task.payload.metadata.get("functionalCases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("缺少正式功能用例快照")
    body: dict[str, Any] = {
        "sourceRoot": str(source_root),
        "functionalCases": cases,
        "cases": cases,
        "taskContext": config.get("uiContext", {}),
        "capabilities": DEFAULT_CAPABILITIES,
    }
    context = dict(config.get("uiContext") or {})
    body["context"] = context
    revision = str(config.get("revisionInstruction") or "").strip()
    if stage != "ui_surface":
        body["surface"] = validate_surface(config.get("uiSurface"), cases)
    if stage == "ui_yaml":
        body["design"] = validate_design(config.get("uiDesign"), cases)
    if revision:
        current = config.get(UI_FIELDS.get(stage, "resultYaml"))
        if current is None:
            raise ValueError("继续优化缺少当前阶段产物")
        body.update(currentArtifact=current, revisionInstruction=revision)
    output_path = workspace.resolve() / "outputs" / f"{stage}.json"
    if stage == "ui_surface":
        if output_path.parent.resolve() != output_path.parent:
            raise ValueError("阶段产物目录不能重定向到其他位置")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.unlink(missing_ok=True)
        body["outputPath"] = str(output_path.resolve())
    inputs = json.dumps(body, ensure_ascii=False)
    if task.payload.extra_instruction.strip():
        inputs += "\n用户生成指令：\n" + task.payload.extra_instruction.strip()
    instruction = (
        "只执行当前阶段 " + stage + "，完成后等待人工审核；不得自动调用其他阶段。"
        "以functionalCases原文定义业务目标。第一步只捕获元素；第二步不以缺定位或缺数据排除用例；"
        "第三步返回YAML，未知字段使用missingFields，保留已知值，不返回阻塞字符串。"
    )
    file_instruction = (
        "请读取并修复输入 outputPath 指定文件，将本阶段完整 JSON 写回同一文件。"
        "最终只需返回 artifactPath 和 status=written 的确认 JSON，不要返回说明或 Markdown。"
    )
    if stage == "ui_surface":
        instruction += file_instruction
        instruction += "固定回执示例：" + json.dumps(
            {"artifactPath": str(output_path), "status": "written"}
        )
    artifact = None
    semantic_review: dict[str, Any] = {}

    def validate(raw: str) -> None:
        nonlocal artifact
        if stage == "ui_yaml":
            validate_yaml(raw)
            artifact = raw
            return
        parsed = read_stage_json(raw, output_path)
        artifact = validate_surface(parsed, cases)

    def report(event: dict) -> None:
        intermediate = dict(config)
        if source_metadata:
            intermediate.update(source_metadata)
        progress_callback(
            TaskProgress(
                task_id=task.task_id,
                attempt_id=task.attempt_id,
                current_stage=stage,
                stage_status="running",
                intermediate_json_text=json.dumps(intermediate, ensure_ascii=False),
                result_summary_json=json.dumps(
                    {"uiWorkflowVersion": UI_WORKFLOW_VERSION, "outputValidation": event}
                ),
            )
        )

    report({"status": "generating"})
    if stage == "ui_design":
        artifact = asyncio.run(
            generate_batches(
                body=body,
                instruction=instruction,
                user_instruction=task.payload.extra_instruction,
                diagnostic_dir=workspace / "diagnostics" / stage,
                report=report,
                generate=lambda prompt, batch, rules: skill_runner(
                    input_text=prompt,
                    session_key=f"{task.session_key}:ui-design:{batch}",
                    skill_name=UI_SKILLS[stage],
                    config_path=config_path,
                    workspace=str(workspace),
                    extra_instruction=rules,
                ),
            )
        )
    elif stage == "ui_yaml":
        artifact = asyncio.run(
            generate_yaml_batches(
                body=body,
                instruction=instruction + yaml_instruction,
                user_instruction=task.payload.extra_instruction,
                diagnostic_dir=workspace / "diagnostics" / stage,
                report=report,
                validate_yaml=validate_yaml,
                review_report=semantic_review.update,
                review=lambda prompt, batch, rules: skill_runner(
                    input_text=prompt,
                    session_key=f"{task.session_key}:ui-yaml-review:{batch}:{uuid4().hex}",
                    skill_name=UI_SKILLS[stage],
                    config_path=config_path,
                    workspace=str(workspace),
                    extra_instruction=rules,
                ),
                generate=lambda prompt, batch, rules: skill_runner(
                    input_text=prompt,
                    session_key=f"{task.session_key}:ui-yaml:{batch}:{uuid4().hex}",
                    skill_name=UI_SKILLS[stage],
                    config_path=config_path,
                    workspace=str(workspace),
                    extra_instruction=rules,
                ),
            )
        )
    else:
        asyncio.run(
            generate_validated(
                stage=stage,
                inputs=inputs,
                generate=lambda prompt: skill_runner(
                    input_text=prompt,
                    session_key=task.session_key,
                    skill_name=UI_SKILLS[stage],
                    config_path=config_path,
                    workspace=str(workspace),
                    extra_instruction=instruction,
                ),
                validate=validate,
                diagnostic_dir=workspace / "diagnostics" / stage,
                report=report,
                **({"repair_instruction": file_instruction} if stage == "ui_surface" else {}),
            )
        )
    effective = {k: v for k, v in config.items() if k not in {"revisionInstruction", "resultYaml"}}
    if source_metadata:
        effective.update(source_metadata)
    if stage in UI_FIELDS:
        effective[UI_FIELDS[stage]] = artifact
        progress_callback(
            TaskProgress(
                task_id=task.task_id,
                attempt_id=task.attempt_id,
                current_stage=stage,
                stage_status="waiting_review",
                intermediate_json_text=json.dumps(effective, ensure_ascii=False),
                output_yaml="",
                result_summary_json=json.dumps(
                    {
                        "uiWorkflowVersion": UI_WORKFLOW_VERSION,
                        "stage": stage,
                        "status": "waiting_review",
                    },
                    ensure_ascii=False,
                ),
            )
        )
        return None
    return TaskResult(
        task_id=task.task_id,
        attempt_id=task.attempt_id,
        generate_task_id=task.generate_task_id,
        status=TaskStatus.SUCCESS,
        intermediate_json_text=json.dumps(effective, ensure_ascii=False),
        output_yaml=artifact,
        result_summary_json=json.dumps(
            {
                "uiWorkflowVersion": UI_WORKFLOW_VERSION,
                "stage": stage,
                "caseCount": validate_yaml(artifact),
                "uiSemanticReview": semantic_review,
            },
            ensure_ascii=False,
        ),
        started_at=started_at,
        finished_at=datetime.now().astimezone(),
    )
