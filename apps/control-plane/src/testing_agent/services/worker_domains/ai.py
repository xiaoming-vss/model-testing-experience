from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from testing_agent.core.enums import RunStatus, StageStatus
from testing_agent.core.errors import ErrBadRequest
from testing_agent.schemas.workers import WorkerTaskEventRequest
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
