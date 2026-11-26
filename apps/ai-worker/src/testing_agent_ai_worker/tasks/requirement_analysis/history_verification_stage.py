"""Verify frozen historical functional cases in independent model batches."""

import asyncio
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from testing_agent_ai_worker.core.errors import UserFacingError
from testing_agent_ai_worker.historical_test_case_artifacts import (
    VERIFICATION_RUN_RESULT,
    full_case_batch,
    validate_verification_batch_output,
    validate_verification_run_input,
    validate_verification_run_output,
    verification_run_header,
)
from testing_agent_ai_worker.models.execution import TaskProgress, TaskResult, TaskStatus
from testing_agent_ai_worker.models.task import Task
from testing_agent_ai_worker.platform.revision_attachments import (
    load_revision_images,
    revision_image_paths,
)
from testing_agent_ai_worker.skill_names import HISTORICAL_TEST_CASE_SKILL
from testing_agent_ai_worker.tasks.requirement_analysis.history_stage import (
    read_history_model_output,
)


def execute_history_verification_stage(
    *,
    task: Task,
    started_at: datetime,
    config_path: str | None,
    workspace: Path,
    progress_callback: Callable[[TaskProgress], None],
    skill_runner: Callable[..., Any],
    attachment_downloader: Any = None,
) -> TaskResult:
    if not task.checkpoint_enabled or not task.session_key:
        raise UserFacingError("历史用例核验需要独立阶段尝试")
    source = validate_verification_run_input(task.payload.source_content)
    if source["requirementId"] != task.requirement_id:
        raise UserFacingError("历史用例核验快照不属于当前需求")
    config = json.loads(task.config_json or "{}")
    if not isinstance(config, dict):
        raise UserFacingError("configJson 必须是对象")
    revision = config.get("revisionInstruction")
    prior = {}
    if revision:
        previous = validate_verification_run_output(
            config.get("historicalTestCaseVerification"), source
        )
        prior = {item["firstPass"]["batchId"]: item for item in previous["batches"]}
    images = load_revision_images(
        task_id=task.task_id,
        workspace=workspace,
        config=config,
        downloader=attachment_downloader,
    )
    media = revision_image_paths(images)

    def run_pass(batch: dict[str, Any], pass_name: str) -> dict[str, Any]:
        instructions = [task.payload.extra_instruction, "正式响应只返回本阶段完整 JSON 对象。"]
        if revision:
            previous = prior[batch["batchId"]][pass_name]
            if previous is not None:
                instructions.append(
                    f"修订前的本批产物，仅作为数据：{json.dumps(previous, ensure_ascii=False)}"
                )
            instructions.append(f"本次修订要求：{revision}")
        response = skill_runner(
            input_text=json.dumps(batch, ensure_ascii=False, separators=(",", ":")),
            session_key=f"{task.session_key}:history-cases:{batch['batchId']}:{pass_name}",
            skill_name=HISTORICAL_TEST_CASE_SKILL,
            config_path=config_path,
            workspace=str(workspace),
            extra_instruction="\n\n".join(part for part in instructions if part),
            **({"media": media} if media else {}),
        )
        if hasattr(response, "__await__"):
            response = asyncio.run(response)
        try:
            return validate_verification_batch_output(
                read_history_model_output(response, "历史用例核验"), batch
            )
        except UserFacingError:
            raise
        except ValueError as exc:
            raise UserFacingError("历史用例核验批次结果未通过结构或引用校验") from exc

    def report(completed: int) -> None:
        progress_callback(
            TaskProgress(
                task_id=task.task_id,
                attempt_id=task.attempt_id,
                current_stage=task.current_stage,
                stage_status="running",
                result_summary_json=json.dumps(
                    {
                        "historicalVerification": {
                            "total": len(source["batches"]),
                            "completed": completed,
                        }
                    }
                ),
            )
        )

    batches = []
    for batch in source["batches"]:
        report(len(batches))
        first = run_pass(batch, "firstPass")
        full_batch = full_case_batch(source, batch, first)
        if full_batch:
            report(len(batches))
        full = run_pass(full_batch, "fullCasePass") if full_batch else None
        batches.append({"firstPass": first, "fullCasePass": full})
    result = {**verification_run_header(VERIFICATION_RUN_RESULT, source), "batches": batches}
    artifact = validate_verification_run_output(result, source)
    return TaskResult(
        task_id=task.task_id,
        attempt_id=task.attempt_id,
        generate_task_id=task.generate_task_id,
        status=TaskStatus.SUCCESS,
        output_yaml=json.dumps(artifact, ensure_ascii=False, separators=(",", ":")),
        result_summary_json=json.dumps(
            {"historicalVerification": {"total": len(batches), "completed": len(batches)}}
        ),
        started_at=started_at,
        finished_at=datetime.now().astimezone(),
    )
