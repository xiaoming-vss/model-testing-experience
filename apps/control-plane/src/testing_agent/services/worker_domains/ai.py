from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.enums import RunStatus, StageStatus
from testing_agent.models.ai_generate_task import AiGenerateTaskRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.schemas.workers import (
    WorkerTaskEventRequest,
)
from testing_agent.services.worker_domains.events import (
    final_run_status,
    json_text,
    parse_event_time,
)


def apply_ai_completion_to_run(
    run: AiGenerateTaskRun | Any, body: WorkerTaskEventRequest, *, functional: bool = False
) -> None:
    snapshot = body.snapshot_json or {}
    status = final_run_status(body.status)
    run.status = status
    current_stage = snapshot.get("currentStage") or snapshot.get("stage")
    if current_stage is not None:
        run.current_stage = str(current_stage)
    stage_status = snapshot.get("stageStatus")
    if stage_status is not None:
        run.stage_status = str(stage_status)
    elif status == RunStatus.SUCCESS.value:
        run.stage_status = StageStatus.COMPLETED.value
        run.current_stage = "completed"
    elif status in {"failed", "error", "canceled"}:
        run.stage_status = StageStatus.FAILED.value
    run.error_message = body.error_message or snapshot.get("errorMessage") or ""
    run.remediation = body.remediation or snapshot.get("remediation") or ""
    if not functional or status == RunStatus.SUCCESS.value:
        if body.config_json is not None:
            run.config_json = body.config_json
        elif snapshot.get("configJson") is not None:
            run.config_json = snapshot.get("configJson")
        output_yaml = getattr(body, "output_yaml", None)
        if body.result_yaml is not None:
            run.result_yaml = body.result_yaml
        elif output_yaml is not None:
            run.result_yaml = output_yaml
        elif snapshot.get("resultYaml") is not None:
            run.result_yaml = str(snapshot.get("resultYaml"))
        elif snapshot.get("outputYaml") is not None:
            run.result_yaml = str(snapshot.get("outputYaml"))
    if body.result_summary_json is not None:
        run.result_summary_json = body.result_summary_json
    elif snapshot.get("resultSummaryJson") is not None:
        run.result_summary_json = snapshot.get("resultSummaryJson")
    run.finished_at = parse_event_time(body.finished_at) or datetime.now(UTC)
    if body.duration_ms is not None:
        run.duration_ms = body.duration_ms


async def build_snapshot(session: AsyncSession, task: WorkerTask) -> dict[str, Any]:
    run = await session.scalar(
        select(AiGenerateTaskRun).where(AiGenerateTaskRun.run_id == task.run_id)
    )
    if run is None:
        return {
            "taskType": task.task_type,
            "checkpointEnabled": False,
            "currentStage": "",
            "configJson": "{}",
            "run": None,
        }
    snapshot = dict(run.snapshot_json or {})
    config = run.config_json or {}
    if isinstance(run, AiGenerateTaskRun):
        from testing_agent.services.ai_execution import worker_input

        ai_run = run
        snapshot, config = await session.run_sync(
            lambda sync_session: worker_input(sync_session, ai_run, task)
        )
    if snapshot:
        snapshot["runId"] = run.run_id
        document_type = snapshot.get("documentType") or snapshot.get("sourceType")
        if snapshot.get("taskType") in {
            "requirement_analysis",
            "functional_case_generate",
        } and document_type in {"text", "word", "docx", "richtext"}:
            document_url = f"/internal/ai-worker/tasks/{task.task_id}/requirement-document"
            snapshot["documentDownloadUrl"] = document_url
            if document_type in {"word", "docx"} and not snapshot.get("sourceContent"):
                snapshot["sourceContent"] = document_url
    return {
        "taskType": task.task_type,
        "checkpointEnabled": run.checkpoint_enabled,
        "currentStage": run.current_stage,
        "configJson": json_text(config),
        "run": snapshot or None,
    }


async def complete_run(
    session: AsyncSession, task: WorkerTask, body: WorkerTaskEventRequest
) -> None:
    run = await session.scalar(
        select(AiGenerateTaskRun).where(AiGenerateTaskRun.run_id == task.run_id)
    )
    if run:
        apply_ai_completion_to_run(
            run, body, functional=task.task_type == "functional_case_generate"
        )
