"""Bounded output repair for both requirement stages, without publishing invalid artifacts."""

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from testing_agent_ai_worker.models.execution import TaskProgress
from testing_agent_ai_worker.models.task import Task
from testing_agent_ai_worker.requirement_artifacts import validate_artifact


def generate_validated(
    *,
    kind: str,
    task: Task,
    stage: str,
    workspace: Path,
    generate: Callable[..., Any],
    arguments: dict[str, Any],
    report: Callable[[TaskProgress], None],
) -> dict[str, Any]:
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
    saved_config = json.loads(task.config_json or "{}")
    saved_output = saved_config.get("resultYaml") or saved_config.get("finalOutput") or ""
    if not isinstance(saved_output, str):
        saved_output = json.dumps(saved_output, ensure_ascii=False)
    instruction = original
    directory = workspace / "diagnostics" / "requirement-output" / uuid4().hex
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
        if truncated:
            error = "模型报告输出长度截断，请调整模型输出限制或缩小材料范围"
        else:
            try:
                artifact = validate_artifact(raw, kind)
                error = None
            except ValueError as exc:
                error = str(exc)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = directory / f"attempt-{attempt}.json"
        with path.open("x", encoding="utf-8") as output:
            path.chmod(0o600)
            json.dump(
                {"stage": stage, "attempt": attempt, "rawResponse": raw, "error": error},
                output,
                ensure_ascii=False,
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
            + "\n保留原材料、业务含义、稳定 ID 和未涉及修改的内容，仅修复校验问题。"
            "业务依据不足时保留未知状态和待确认问题，不编造事实、来源或确认答复，"
            "不为通过校验删除有效业务内容或未回答的问题。"
            "返回本阶段完整 JSON，不返回修改片段或额外说明。"
        )
    raise AssertionError("unreachable")
