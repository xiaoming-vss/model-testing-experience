"""Read normalized execution records and build the existing wire projection; no writes."""

import json
from collections.abc import Sequence
from copy import deepcopy
from datetime import UTC
from typing import Any, overload

from sqlalchemy import select
from sqlalchemy.orm import Session

from testing_agent.core.errors import ErrNotFound
from testing_agent.domain.ai_execution_format import FIELDS, extra_config, final_stage, mapping
from testing_agent.models.ai_generate_execution import AiGenerateRunImport as Import
from testing_agent.models.ai_generate_execution import AiGenerateRunStage as Stage
from testing_agent.models.ai_generate_execution import AiGenerateStageAttempt as Attempt
from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
from testing_agent.models.worker_task import WorkerTask


def graph(session: Session, run: AiGenerateTaskRun) -> tuple[list[Stage], dict[str, Attempt]]:
    stages = list(
        session.scalars(select(Stage).where(Stage.run_id == run.run_id).order_by(Stage.stage_order))
    )
    attempts = list(
        session.scalars(
            select(Attempt)
            .join(Stage, Stage.id == Attempt.stage_id)
            .where(Stage.run_id == run.run_id)
        )
    )
    return stages, {a.id: a for a in attempts}


@overload
def project(session: Session, run: AiGenerateTaskRun) -> AiGenerateTaskRun: ...


@overload
def project(session: Session, run: None) -> None: ...


def project(session: Session, run: AiGenerateTaskRun | None) -> AiGenerateTaskRun | None:
    """Read effective artifacts from normalized records, keeping wire names unchanged."""
    if run is None:
        return run
    scope = session.execute(
        select(
            AiGenerateTask.project_id, AiGenerateTask.sprint_id, AiGenerateTask.requirement_id
        ).where(AiGenerateTask.task_id == run.task_id)
    ).first()
    apply_scope(run, scope)
    stages, attempts = graph(session, run)
    imported = session.scalar(select(Import).where(Import.run_id == run.run_id))
    return _project(run, stages, attempts, imported)


def _project(
    run: AiGenerateTaskRun,
    stages: list[Stage],
    attempts: dict[str, Attempt],
    imported: Import | None,
) -> AiGenerateTaskRun:
    if not stages:
        raise ErrNotFound()
    final = final_stage(stages)
    current = next(
        (stage for stage in stages if stage.stage == run.current_stage),
        final if run.current_stage == "completed" else stages[0],
    )
    latest = max(
        (a for a in attempts.values() if a.stage_id == current.id),
        key=lambda a: a.attempt_no,
        default=None,
    )
    config = extra_config(
        latest.output_context_json
        if latest and latest.output_context_json is not None
        else mapping(latest.input_snapshot_json).get("config", {})
        if latest
        else {}
    )
    for stage in stages:
        artifact = attempts.get(stage.current_artifact_attempt_id or "")
        if artifact is None or artifact.stage_id != stage.id:
            continue
        value = artifact.output_content
        if stage.stage in FIELDS:
            if artifact.output_format == "json":
                if value is None:
                    raise ValueError("JSON artifact has no content")
                value = json.loads(value)
            config[FIELDS[stage.stage]] = value
        elif stage is final:
            run.result_yaml = value or ""
    current = next(
        (stage for stage in stages if stage.stage == run.current_stage),
        final if run.current_stage == "completed" else stages[0],
    )
    latest = max(
        (a for a in attempts.values() if a.stage_id == current.id),
        key=lambda a: a.attempt_no,
        default=None,
    )
    if latest:
        if latest.status in {"pending", "running", "failed", "error", "canceled"}:
            if latest.revision_instruction:
                config["revisionInstruction"] = latest.revision_instruction
        else:
            config.pop("revisionInstruction", None)
        run.error_message = latest.error_message or ""
        run.remediation = latest.remediation or ""
        if latest.progress_json is not None:
            run.result_summary_json = deepcopy(latest.progress_json)
    if run.current_stage:
        status = current.execution_status
        stage_status = (
            ("waiting_review" if run.status == "waiting_review" else "completed")
            if status == "success"
            else status
        )
        run.stage_status = stage_status
    run.config_json = config
    if final.review_status != "not_required":
        for field, field_value in (
            ("review_status", final.review_status),
            ("reviewer_user_id", final.reviewer_user_id or ""),
            ("reviewed_at", final.reviewed_at),
            ("review_comment", final.review_comment or ""),
        ):
            setattr(run, field, field_value)
    run.import_status = "imported" if imported else "pending"
    run.imported_targets = imported.imported_targets_json or [] if imported else []
    run.imported_at = imported.imported_at if imported else None
    if run.started_at and run.finished_at:
        end = (
            run.finished_at.replace(tzinfo=UTC)
            if run.finished_at.tzinfo is None
            else run.finished_at
        )
        start = (
            run.started_at.replace(tzinfo=UTC) if run.started_at.tzinfo is None else run.started_at
        )
        elapsed = end - start
        run.duration_ms = max(0, int(elapsed.total_seconds() * 1000))

    def aware(value):
        return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value

    timestamps = [aware(run.created_at), *[aware(s.updated_at) for s in stages]]
    if latest:
        timestamps.append(aware(latest.created_at))
    if imported:
        timestamps.append(aware(imported.imported_at or imported.created_at))
    run.history_updated_at = max((t for t in timestamps if t), default=None)
    return run


def worker_input(
    session: Session, run: AiGenerateTaskRun, task: WorkerTask
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the exact dispatch input, not the current effective UI artifact."""
    row = session.scalar(
        select(Attempt)
        .join(Stage, Stage.id == Attempt.stage_id)
        .where(Stage.run_id == run.run_id, Attempt.worker_task_id == task.task_id)
        .order_by(Stage.stage_order.desc())
    )
    if row is None:
        return deepcopy(run.snapshot_json or {}), mapping(run.config_json)
    inputs = mapping(row.input_snapshot_json)
    config = mapping(inputs.get("config"))
    config.pop("revisionInstruction", None)
    if row.revision_instruction:
        config["revisionInstruction"] = row.revision_instruction
    return mapping(inputs.get("source")), config


def project_many(session: Session, runs: list[AiGenerateTaskRun]) -> list[AiGenerateTaskRun]:
    """Three batched reads instead of three reads per run on history pages."""
    if not runs:
        return runs
    scopes = {
        row[0]: row[1:]
        for row in session.execute(
            select(
                AiGenerateTask.task_id,
                AiGenerateTask.project_id,
                AiGenerateTask.sprint_id,
                AiGenerateTask.requirement_id,
            ).where(AiGenerateTask.task_id.in_({r.task_id for r in runs}))
        )
    }
    for run in runs:
        apply_scope(run, scopes.get(run.task_id))
    ids = [run.run_id for run in runs]
    stages = list(
        session.scalars(select(Stage).where(Stage.run_id.in_(ids)).order_by(Stage.stage_order))
    )
    attempts = {
        a.id: a
        for a in session.scalars(
            select(Attempt).join(Stage, Stage.id == Attempt.stage_id).where(Stage.run_id.in_(ids))
        )
    }
    imports = {i.run_id: i for i in session.scalars(select(Import).where(Import.run_id.in_(ids)))}
    grouped: dict[str, list[Stage]] = {run_id: [] for run_id in ids}
    for stage in stages:
        grouped[stage.run_id].append(stage)
    return [_project(run, grouped[run.run_id], attempts, imports.get(run.run_id)) for run in runs]


def apply_scope(run: AiGenerateTaskRun, scope: Sequence[Any] | None) -> None:
    if scope is None:
        raise ErrNotFound()
    run.project_id, run.sprint_id, run.requirement_id = scope
    run.trigger_type = "manual"  # retained only as a legacy wire default
