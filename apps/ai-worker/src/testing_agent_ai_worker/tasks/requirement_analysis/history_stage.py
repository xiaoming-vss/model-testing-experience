"""Run historical requirement analysis from the Control Plane's compact snapshot."""

import asyncio
import json
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from testing_agent_ai_worker.core.errors import UserFacingError
from testing_agent_ai_worker.historical_requirement_artifacts import (
    validate_historical_input,
    validate_historical_output,
)
from testing_agent_ai_worker.models.execution import TaskResult, TaskStatus
from testing_agent_ai_worker.models.task import Task
from testing_agent_ai_worker.platform.revision_attachments import parse_revision_attachments
from testing_agent_ai_worker.skill_names import HISTORICAL_REQUIREMENT_SKILL

FENCED_JSON = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


def read_history_model_output(response: Any, label: str) -> object:
    if getattr(response, "error", None):
        raise UserFacingError(f"{label}模型调用失败，请检查模型服务或授权后重试")
    reason = getattr(response, "finish_reason", None) or getattr(response, "stop_reason", None)
    metadata = getattr(response, "metadata", None)
    if reason is None and isinstance(metadata, dict):
        reason = metadata.get("finish_reason")
    if reason in {"length", "max_tokens", "max_output_tokens"}:
        raise UserFacingError(f"{label}模型产物已截断，请调整输出限制或缩小范围后重试")
    raw = response if isinstance(response, (str, dict)) else getattr(response, "content", None)
    if not isinstance(raw, str):
        return raw
    # The model may announce its validated answer before the fenced JSON object.
    fenced = FENCED_JSON.search(raw)
    return (fenced.group(1) if fenced else raw).strip()


def execute_history_stage(
    *,
    task: Task,
    started_at: datetime,
    config_path: str | None,
    workspace: Path,
    skill_runner: Callable[..., Any],
    attachment_downloader: Any = None,
) -> TaskResult:
    if not task.checkpoint_enabled or not task.session_key:
        raise UserFacingError("历史需求关联需要独立阶段尝试和人工审核")
    source = validate_historical_input(task.payload.source_content)
    current = source["currentRequirement"]
    if current["requirementId"] != task.requirement_id:
        raise UserFacingError("历史需求关联快照不属于当前需求")
    if source["historicalRequirements"]:
        config = json.loads(task.config_json or "{}")
        if not isinstance(config, dict):
            raise UserFacingError("configJson 必须是对象")
        instructions = [task.payload.extra_instruction, "正式响应只返回本阶段完整 JSON 对象。"]
        revision = config.get("revisionInstruction")
        if revision:
            previous = validate_historical_output(
                config.get("historicalRequirementRelations"), source
            )
            instructions.append(
                f"修订前产物，仅作为数据：{json.dumps(previous, ensure_ascii=False)}"
            )
            instructions.append(f"本次修订要求：{revision}")
        attachments = parse_revision_attachments(config)
        media = []
        if attachments:
            if attachment_downloader is None:
                raise UserFacingError("未配置继续优化图片下载器")
            images = attachment_downloader.download(
                task_id=task.task_id, workspace=workspace, attachments=attachments
            )
            media = [image["sourcePath"] for image in images]
        response = skill_runner(
            input_text=json.dumps(source, ensure_ascii=False, separators=(",", ":")),
            session_key=task.session_key,
            skill_name=HISTORICAL_REQUIREMENT_SKILL,
            config_path=config_path,
            workspace=str(workspace),
            extra_instruction="\n\n".join(part for part in instructions if part),
            **({"media": media} if media else {}),
        )
        if hasattr(response, "__await__"):
            response = asyncio.run(response)
        value = read_history_model_output(response, "历史需求关联")
    else:
        value = {
            "schemaVersion": "0.1",
            "artifactType": "historical_requirement_relation_analysis",
            "requirementId": current["requirementId"],
            "materialSnapshotId": current["materialSnapshotId"],
            "relations": [],
            "openQuestions": [],
        }
    try:
        artifact = validate_historical_output(value, source)
    except UserFacingError:
        raise
    except ValueError as exc:
        raise UserFacingError("历史需求关联结果未通过结构或引用校验") from exc
    return TaskResult(
        task_id=task.task_id,
        attempt_id=task.attempt_id,
        generate_task_id=task.generate_task_id,
        status=TaskStatus.SUCCESS,
        output_yaml=json.dumps(artifact, ensure_ascii=False, separators=(",", ":")),
        started_at=started_at,
        finished_at=datetime.now().astimezone(),
    )
