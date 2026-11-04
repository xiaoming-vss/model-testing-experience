"""Project a single independent execution without mixing other runs' artifacts."""

import json
from copy import deepcopy
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrNotFound
from testing_agent.domain.ai_execution_format import FIELDS, final_review_stage, mapping
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.repositories.standalone_execution import workflow_records
from testing_agent.repositories.standalone_import import import_records
from testing_agent.services.standalone_execution import workflow_stage_names
from testing_agent.services.standalone_run import StandaloneRun


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


async def project_standalone_execution(session: AsyncSession, execution_id: str) -> StandaloneRun:
    records = await workflow_records(session, execution_id)
    if records is None:
        raise ErrNotFound()
    execution, task, rows = records
    if execution.workflow_status is None:
        raise ErrNotFound()
    source = deepcopy(execution.source_snapshot_json or {})
    stages = workflow_stage_names(task.task_type, source)
    final_name = final_review_stage(task.task_type, stages)
    current_name = execution.current_stage or stages[0]
    if current_name == "completed":
        current_name = final_name
    by_stage: dict[str, list[AiGenerationAttempt]] = {name: [] for name in stages}
    for stage_name, attempt in rows:
        if stage_name in by_stage:
            by_stage[stage_name].append(attempt)
    latest = by_stage.get(current_name, [])
    current = latest[-1] if latest else None
    initial = rows[0][1] if rows else None
    snapshot_attempt = current or initial
    input_snapshot = snapshot_attempt.input_snapshot_json if snapshot_attempt is not None else {}
    config = mapping((input_snapshot or {}).get("config"))
    artifacts = {}
    for name, attempts in by_stage.items():
        valid = [
            attempt
            for attempt in attempts
            if attempt.status == "success" and attempt.output_content and not attempt.invalidated_at
        ]
        if valid:
            artifacts[name] = valid[-1]
    for name, attempt in artifacts.items():
        field = FIELDS.get(name)
        if field:
            value = attempt.output_content or ""
            config[field] = json.loads(value) if attempt.output_format == "json" else value
    final = artifacts.get(final_name)
    run = StandaloneRun(
        run_id=execution.execution_id,
        task_id=task.task_id,
        trigger_user_id=execution.requested_by,
        status=execution.workflow_status,
        checkpoint_enabled=bool(execution.checkpoint_enabled),
        current_stage=execution.current_stage or "",
        snapshot_json=source,
        created_at=execution.created_at,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
    )
    run.project_id = task.project_id
    run.sprint_id = task.sprint_id
    run.requirement_id = task.requirement_id
    run.trigger_type = execution.trigger_type or "manual"
    run.config_json = config
    run.result_yaml = str(final.output_content or "") if final else ""
    run.result_summary_json = deepcopy(final.output_context_json or {}) if final else {}
    run.error_message = (current.error_message or "") if current else ""
    run.review_status = str(final.review_status or "pending") if final else "pending"
    if run.review_status == "not_required":
        run.review_status = "pending"
    run.reviewer_user_id = (final.reviewer_user_id or "") if final else ""
    run.reviewed_at = final.reviewed_at if final else None
    run.review_comment = (final.review_comment or "") if final else ""
    if final is not None:
        imports = await import_records(session, final.id)
        if imports:
            run.import_status = "imported"
            run.imported_at = imports[-1].imported_at
            seen = set()
            for record in imports:
                key = (record.target_type, record.target_id)
                if key not in seen:
                    run.imported_targets.append({"targetType": key[0], "targetId": key[1]})
                    seen.add(key)
    if current:
        run.stage_status = (
            "waiting_review"
            if current.status == "success" and run.status == "waiting_review"
            else "completed"
            if current.status == "success"
            else current.status
        )
    times = [
        _aware(execution.created_at),
        _aware(execution.started_at),
        _aware(execution.finished_at),
    ]
    times.extend(_aware(attempt.created_at) for _, attempt in rows)
    run.history_updated_at = max((value for value in times if value is not None), default=None)
    if execution.started_at and execution.finished_at:
        start, end = _aware(execution.started_at), _aware(execution.finished_at)
        if start and end:
            run.duration_ms = max(0, int((end - start).total_seconds() * 1000))
    return run
