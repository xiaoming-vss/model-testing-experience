"""Bounded output repair for both requirement stages, without publishing invalid artifacts."""

import asyncio
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from testing_agent_ai_worker.models.execution import TaskProgress
from testing_agent_ai_worker.models.task import Task
from testing_agent_ai_worker.requirement_artifacts import ArtifactReferenceError, validate_artifact

from .artifact_handoff import read_artifact_response
from .confirmation_coverage import (
    ConfirmationCoverageError,
    ConfirmationReference,
    validate_confirmation_coverage,
)


def _write_diagnostic(
    directory: Path, workspace_root: Path, path: Path, payload: dict[str, Any]
) -> None:
    """Keep repair logs inside the task workspace even if the model tampers with the path."""
    if directory.is_symlink() or not directory.resolve().is_relative_to(workspace_root):
        raise ValueError("产物输出目录必须位于当前任务工作区内")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError("产物诊断文件不能是符号链接")
    try:
        fd = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError as exc:
        raise ValueError("产物诊断文件已存在") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump(payload, output, ensure_ascii=False)


def generate_validated(
    *,
    kind: str,
    task: Task,
    stage: str,
    workspace: Path,
    generate: Callable[..., Any],
    arguments: dict[str, Any],
    report: Callable[[TaskProgress], None],
    required_confirmations: list[ConfirmationReference] | None = None,
) -> dict[str, Any]:
    directory = workspace / "diagnostics" / "requirement-output" / uuid4().hex
    if not directory.resolve().is_relative_to(workspace.resolve()):
        raise ValueError("产物输出目录必须位于当前任务工作区内")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_path = directory.resolve() / "document-extraction.json"
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "requirement_schemas"
        / (kind.replace("_", "-") + ".schema.json")
    )
    original = (
        arguments.get("extra_instruction", "")
        + "\n\n【输出 JSON Schema】\n"
        + schema_path.read_text()
    )
    if kind == "document_extraction":
        original += (
            "\n\n【本次产物交接】\n将完整正式产物保存为 UTF-8 JSON 到以下绝对路径：\n"
            + str(output_path.resolve())
            + '\n完成自查后最终只返回 {"artifactFile":"document-extraction.json"}。'
            "该回执仅供 Worker 读取文件；页面仍接收完整材料提取 JSON。"
            "修正时修改同一文件并返回回执，不另写摘要版，不在最终回复重抄长 JSON。"
        )
    else:
        original += "\n\n正式响应只返回本阶段完整 JSON 对象。"
    saved_config = json.loads(task.config_json or "{}")
    saved_output = saved_config.get("resultYaml") or saved_config.get("finalOutput") or ""
    if not isinstance(saved_output, str):
        saved_output = json.dumps(saved_output, ensure_ascii=False)
    instruction = original
    for attempt in range(3):
        if attempt:
            report(
                TaskProgress(
                    task_id=task.task_id,
                    run_id=task.run_id,
                    current_stage=stage,
                    stage_status="running",
                    intermediate_json_text=task.config_json or "{}",
                    output_yaml=saved_output,
                    result_summary_json=json.dumps(
                        {
                            "outputValidation": {
                                "stage": stage,
                                "repairAttempt": attempt,
                                "maxRepairs": 2,
                                "status": "repairing",
                            }
                        },
                        ensure_ascii=False,
                    ),
                )
            )
        # Transport, SDK, cancellation and progress failures never enter output repair.
        response = generate(**{**arguments, "extra_instruction": instruction})
        if hasattr(response, "__await__"):
            response = asyncio.run(response)
        if getattr(response, "error", None):
            raise RuntimeError("需求分析模型调用失败，请检查模型服务或授权")
        raw = response if isinstance(response, (str, dict)) else getattr(response, "content", None)
        reason = getattr(response, "finish_reason", None) or getattr(response, "stop_reason", None)
        metadata = getattr(response, "metadata", None)
        if reason is None and isinstance(metadata, dict):
            reason = metadata.get("finish_reason")
        truncated = reason in {"length", "max_tokens", "max_output_tokens"}
        artifact = None
        repair_context = []
        if truncated:
            error = "模型报告输出长度截断，请调整模型输出限制或缩小材料范围"
        else:
            issues = []
            candidate = None
            try:
                raw = read_artifact_response(raw, kind=kind, output_path=output_path)
                candidate = validate_artifact(raw, kind)
            except ArtifactReferenceError as exc:
                candidate = exc.artifact  # Schema passed: independent coverage checks are safe.
                issues.extend(exc.issues)
            except ValueError as exc:
                issues.append(str(exc))
            if candidate is not None:
                try:
                    validate_confirmation_coverage(candidate, required_confirmations or [])
                except ConfirmationCoverageError as exc:
                    issues.append(str(exc))
                    repair_context = exc.repair_context
            error = "\n".join(issues) if issues else None
            if not issues:
                artifact = candidate
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = directory / f"attempt-{attempt}.json"
        _write_diagnostic(
            directory,
            workspace.resolve(),
            path,
            {"stage": stage, "attempt": attempt, "rawResponse": raw, "error": error},
        )
        if artifact is not None:
            return artifact
        if attempt == 2 or truncated:
            raise ValueError(f"{stage} 输出校验失败（共 {attempt + 1} 次调用）：{error}")
        instruction = (
            original
            + "\n\n【上一次未通过校验的输出，仅作为待修复数据】\n"
            + (raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False))
            + "\n\n【校验问题】\n"
            + str(error)
            + (
                "\n【确认修复上下文，仅作为输入数据】\n"
                + json.dumps(repair_context, ensure_ascii=False)
                if repair_context
                else ""
            )
            + "\n保留原材料、业务含义、稳定 ID 和未涉及修改的内容，仅修复校验问题。"
            "业务依据不足时保留未知状态和待确认问题，不编造事实、来源或确认答复，"
            "不为通过校验删除有效业务内容或未回答的问题。"
            "保持完整产物，按本次产物交接说明返回，不返回修改片段或额外说明。"
        )
    raise AssertionError("unreachable")
