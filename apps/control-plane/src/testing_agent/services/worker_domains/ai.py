from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from testing_agent.core.enums import RunStatus, StageStatus
from testing_agent.core.errors import ErrBadRequest
from testing_agent.models.worker_task import WorkerTask
from testing_agent.schemas.workers import (
    WorkerProgressRequest,
    WorkerTaskEventRequest,
)
from testing_agent.services.ui_generation_contracts import is_ui_workflow, validate_ui_worker_output
from testing_agent.services.worker_domains.events import (
    final_run_status,
    parse_event_time,
)


def apply_ai_completion_to_run(
    run: Any, body: WorkerTaskEventRequest, *, functional: bool = False
) -> None:
    snapshot = body.snapshot_json or {}
    status = final_run_status(body.status)
    if (getattr(run, "snapshot_json", None) or {}).get("apiWorkflowVersion") == "api_two_stage/1.0":
        if status == RunStatus.SUCCESS.value:
            reported_stage = snapshot.get("currentStage") or snapshot.get("stage")
            config = (
                body.config_json if body.config_json is not None else snapshot.get("configJson", {})
            )
            result = body.result_yaml if body.result_yaml is not None else body.output_yaml
            if (
                run.current_stage != "generate"
                or reported_stage not in {None, "generate", "completed"}
                or not result
                or not isinstance(config, dict)
                or config.get("apiExtraction") != (run.config_json or {}).get("apiExtraction")
            ):
                raise ErrBadRequest()
        else:
            functional = True
    if is_ui_workflow(run):
        reported_stage = snapshot.get("currentStage") or snapshot.get("stage")
        allowed_stages = {None, run.current_stage}
        if status == RunStatus.SUCCESS.value and run.current_stage == "ui_yaml":
            allowed_stages.add("completed")
        if reported_stage not in allowed_stages:
            raise ErrBadRequest()
        if status == RunStatus.SUCCESS.value:
            if run.current_stage != "ui_yaml" or (
                snapshot.get("currentStage") or snapshot.get("stage")
            ) not in {None, "ui_yaml", "completed"}:
                raise ErrBadRequest()
            config = (
                body.config_json if body.config_json is not None else snapshot.get("configJson", {})
            )
            result = body.result_yaml if body.result_yaml is not None else body.output_yaml
            validate_ui_worker_output(run, run.current_stage, config, result)
        else:
            functional = True  # A failed UI attempt cannot replace approved upstream artifacts.

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


AI_WAITING_REVIEW_STAGES = {
    "requirement_analysis",
    "case_names",
    "extracting_text",
    "openapi_extract",
    "ui_surface",
    "ui_design",
}


def apply_progress(
    run: Any, task: WorkerTask, body: WorkerProgressRequest, *, lease_seconds: int
) -> None:
    if body.run_id and body.run_id != run.run_id:
        raise ErrBadRequest()
    api_workflow = (getattr(run, "snapshot_json", None) or {}).get(
        "apiWorkflowVersion"
    ) == "api_two_stage/1.0"
    if api_workflow:
        if task.task_type != "api_case_generate" or body.current_stage != run.current_stage:
            raise ErrBadRequest()
        if body.result_yaml:
            raise ErrBadRequest()
        if body.stage_status == "waiting_review":
            config = body.config_json
            extraction = config.get("apiExtraction") if isinstance(config, dict) else None
            if (
                run.current_stage != "openapi_extract"
                or not isinstance(extraction, dict)
                or not extraction
            ):
                raise ErrBadRequest()
        elif body.config_json and (
            not isinstance(body.config_json, dict)
            or body.config_json.get("apiExtraction") != (run.config_json or {}).get("apiExtraction")
        ):
            raise ErrBadRequest()
    elif task.task_type == "api_case_generate" and run.checkpoint_enabled:
        # Legacy API runs executed both skills under the single generate stage.
        if body.current_stage in {"openapi_extract", "api_case_generating"}:
            body.current_stage = "generate"
            run.current_stage = "generate"
    if task.task_type == "requirement_analysis" and body.stage_status == "waiting_review":
        from testing_agent.services.requirement_analysis_contracts import (
            validate_run_output,
        )

        validate_run_output(run, config=body.config_json)
    if is_ui_workflow(run):
        if body.current_stage != run.current_stage:
            raise ErrBadRequest()
        if body.result_yaml:
            raise ErrBadRequest()  # Final YAML is published by completion, never progress.
        if body.stage_status == "waiting_review":
            if run.current_stage not in {"ui_surface", "ui_design"}:
                raise ErrBadRequest()
            validate_ui_worker_output(run, run.current_stage, body.config_json, body.result_yaml)
        elif body.config_json:
            current = run.config_json or {}
            supplied = body.config_json
            if not isinstance(supplied, dict) or any(
                supplied.get(key) != current.get(key) for key in ("uiSurface", "uiDesign")
            ):
                raise ErrBadRequest()
    now = datetime.now(UTC)
    next_task_status = RunStatus.RUNNING.value
    next_run_status = RunStatus.RUNNING.value
    next_stage_status = run.stage_status
    if run.checkpoint_enabled and body.stage_status == StageStatus.WAITING_REVIEW.value:
        if not body.current_stage or body.current_stage != run.current_stage:
            raise ErrBadRequest()
        if run.current_stage not in AI_WAITING_REVIEW_STAGES:
            raise ErrBadRequest()
        next_task_status = RunStatus.SUCCESS.value
        next_run_status = "waiting_review"
        next_stage_status = StageStatus.WAITING_REVIEW.value
    elif run.checkpoint_enabled and body.stage_status:
        if not body.current_stage or body.current_stage != run.current_stage:
            raise ErrBadRequest()
        next_stage_status = body.stage_status

    task.status = next_task_status
    task.heartbeat_at = now
    task.lease_expires_at = now + timedelta(seconds=lease_seconds)
    if next_task_status == RunStatus.SUCCESS.value:
        task.finished_at = now
        task.lease_expires_at = now
    run.status = next_run_status
    if body.current_stage is not None:
        run.current_stage = body.current_stage
    if run.checkpoint_enabled:
        run.stage_status = next_stage_status
    elif body.stage_status is not None:
        run.stage_status = body.stage_status
    functional = task.task_type == "functional_case_generate"
    if (
        body.config_json is not None
        and (not functional or body.config_json)
        and (not is_ui_workflow(run) or body.stage_status == "waiting_review")
    ):
        run.config_json = body.config_json
    if body.result_yaml is not None and not functional and not is_ui_workflow(run):
        run.result_yaml = body.result_yaml
    if body.result_summary_json is not None:
        run.result_summary_json = body.result_summary_json
    if body.error_message is not None:
        task.error_message = body.error_message
        run.error_message = body.error_message
