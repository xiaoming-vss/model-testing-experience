"""Transactional stage/attempt storage and the legacy wire projection.

Only the two AI-aware repositories invoke persist() before committing. Legacy
wire attributes are ordinary properties, not main-table columns. Queue rows,
stage pointers and imports commit together. No ORM global hooks.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from testing_agent.core.errors import ErrBadRequest, ErrNotFound
from testing_agent.models.ai_generate_execution import (
    AiGenerateRunImport as Import,
)
from testing_agent.models.ai_generate_execution import (
    AiGenerateRunStage as Stage,
)
from testing_agent.models.ai_generate_execution import (
    AiGenerateStageAttempt as Attempt,
)
from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
from testing_agent.models.worker_task import WorkerTask

FIELDS = {
    "requirement_analysis": "requirementAnalysis",
    "case_names": "caseNames",
    "extracting_text": "firstStepOutput",
    "writing_requirement": "secondStepOutput",
    "relation_analysis": "caseRelations",
}
TERMINAL = {"success", "failed", "error", "canceled"}
# 派生产物不需要人工审核：功能链路的图谱阶段，以及整体就是派生产物的测试单图谱任务。
NO_REVIEW_STAGES = {"relation_analysis"}
NO_REVIEW_KINDS = {"test_order_graph"}


def ident():
    return str(uuid4())


def mapping(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return deepcopy(value) if isinstance(value, dict) else {}


def content(value):
    if value is None:
        return None
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def extra_config(config):
    return {
        k: deepcopy(v)
        for k, v in mapping(config).items()
        if k not in {*FIELDS.values(), "revisionInstruction", "resultYaml"}
    }


def output_format(value):
    try:
        json.loads(value)
        return "json"
    except (ValueError, TypeError):
        return "text"


def layout(kind):
    if kind == "functional_case_generate":
        return [
            "requirement_analysis",
            "case_names",
            "detailed_cases",
            "relation_analysis",
        ]
    if kind == "requirement_analysis":
        return ["extracting_text", "writing_requirement", "feature_understanding"]
    return ["generate"]


def final_stage(stages):
    """detailed_cases 携带 resultYaml 与运行级审核；relation_analysis 只是派生产物。"""

    for stage in stages:
        if stage.stage == "detailed_cases":
            return stage
    return stages[-1]


def graph(session, run):
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


def new_attempt(session, stage, attempts, run, *, worker=None, operation="generate"):
    siblings = [a for a in attempts.values() if a.stage_id == stage.id]
    snapshot = {
        "source": deepcopy(run.snapshot_json),
        "config": mapping(run.config_json),
        "currentOutput": run.result_yaml or "",
    }
    instruction = snapshot["config"].pop("revisionInstruction", None)
    from testing_agent.services.worker_context import connection_for_attempt

    snapshot["llmConnectionId"] = connection_for_attempt(session, worker)
    previous = max(siblings, key=lambda a: a.attempt_no, default=None)
    if operation == "retry" and previous and previous.status in {"failed", "error", "canceled"}:
        snapshot = mapping(previous.input_snapshot_json)
        instruction = previous.revision_instruction
        snapshot["config"] = mapping(snapshot.get("config"))
        snapshot["config"].pop("revisionInstruction", None)
    snapshot["llmConnectionId"] = connection_for_attempt(session, worker)
    prior_dispatch = next(
        (a for a in attempts.values() if worker and a.worker_task_id == worker.task_id), None
    )
    attempt = Attempt(
        id=ident(),
        stage_id=stage.id,
        attempt_no=max((a.attempt_no for a in siblings), default=0) + 1,
        operation=operation,
        worker_task_id=worker.task_id if worker else None,
        requested_by=(prior_dispatch.requested_by if prior_dispatch else None)
        or getattr(run, "_actor", None)
        or run.trigger_user_id,
        input_snapshot_json=snapshot,
        revision_instruction=instruction,
        status="pending",
        created_at=datetime.now(UTC),
    )
    session.add(attempt)
    attempts[attempt.id] = attempt
    return attempt


def ensure_stages(session, run, kind):
    stages, attempts = graph(session, run)
    if stages:
        return stages, attempts
    names = layout(kind)
    for i, name in enumerate(names):
        if name in NO_REVIEW_STAGES or kind in NO_REVIEW_KINDS:
            review_status = "not_required"
        elif run.checkpoint_enabled or name == final_review_stage(kind, names):
            review_status = "pending"
        else:
            review_status = "not_required"
        stage = Stage(
            id=ident(),
            run_id=run.run_id,
            stage=name,
            stage_order=i,
            execution_status="pending",
            review_status=review_status,
        )
        session.add(stage)
        stages.append(stage)
    session.flush()
    return stages, attempts


def final_review_stage(kind, names):
    """非 checkpoint 运行只有最终产物阶段承接运行级审核。"""

    return "detailed_cases" if kind == "functional_case_generate" else names[-1]


def publish(attempt, stage, value):
    attempt.output_content = content(value)
    attempt.output_format = output_format(attempt.output_content)
    attempt.status = "success"
    stage.current_artifact_attempt_id = attempt.id
    stage.execution_status = "success"
    if stage.active_attempt_id == attempt.id:
        stage.active_attempt_id = None


def sync_run(session, run):
    kind = session.scalar(
        select(AiGenerateTask.task_type).where(AiGenerateTask.task_id == run.task_id)
    )
    stages, attempts = ensure_stages(session, run, kind)
    by_name = {s.stage: s for s in stages}
    stage_by_id = {s.id: s for s in stages}
    final = final_stage(stages)
    current = by_name.get(
        run.current_stage, final if run.current_stage == "completed" else stages[0]
    )
    worker = session.scalar(
        select(WorkerTask)
        .where(WorkerTask.domain == "ai", WorkerTask.run_id == run.run_id)
        .order_by(WorkerTask.created_at.desc(), WorkerTask.id.desc())
    )
    config = mapping(run.config_json)
    operation = getattr(run, "_operation", None)
    # One queue dispatch may span all stages when checkpoints are disabled.
    queued = worker is not None and (
        worker.status in {"pending", "claimed", "running"}
        or getattr(run, "_worker_event", None) == worker.task_id
    )
    if queued:
        match = next(
            (
                a
                for a in attempts.values()
                if a.stage_id == current.id and a.worker_task_id == worker.task_id
            ),
            None,
        )
        if match is None:
            # A follow-up stage's worker (relation analysis) may finish while the run
            # pointer already moved on; the worker's own attempt decides the stage.
            existing = next(
                (
                    a
                    for a in attempts.values()
                    if a.worker_task_id == worker.task_id
                    and stage_by_id[a.stage_id].stage_order > current.stage_order
                ),
                None,
            )
            if existing is not None:
                current = stage_by_id[existing.stage_id]
                match = existing
        if match is None:
            if not getattr(run, "_worker_event", None):
                run.result_summary_json = {}
                run.error_message = ""
                run.remediation = ""
                run.finished_at = None
            match = new_attempt(
                session,
                current,
                attempts,
                run,
                worker=worker,
                operation=operation
                or ("revise" if config.get("revisionInstruction") else "generate"),
            )
        current.active_attempt_id = match.id
        if match.status != "success":
            match.status = "running" if worker.status in {"claimed", "running"} else "pending"
        if match.started_at is None and worker.status in {"claimed", "running"}:
            match.started_at = worker.started_at or datetime.now(UTC)
    active = attempts.get(current.active_attempt_id)
    review = getattr(run, "_stage_review", None)
    if review:
        reviewed_stage = by_name[review[0]]
        reviewed_stage.review_status = review[1]
        reviewed_stage.reviewer_user_id = getattr(run, "_actor", None)
        reviewed_stage.reviewed_at = datetime.now(UTC)
        reviewed_stage.review_comment = review[2]

    for stage in stages:
        value = config.get(FIELDS.get(stage.stage)) if stage is not final else run.result_yaml
        if value is None or value == "":
            continue
        old = attempts.get(stage.current_artifact_attempt_id)
        if old and stage.stage_order < current.stage_order:
            stage.execution_status = "success"
            stage.active_attempt_id = None
        if old and run.status in {"failed", "error", "canceled"}:
            continue
        # Revision input is a draft, never a new effective artifact before success.
        if stage is current and (
            operation in {"revise", "retry"}
            or (
                active
                and active.operation in {"revise", "retry"}
                and run.status not in {"success", "waiting_review"}
            )
        ):
            continue
        # Running detailed output is never publishable. Unchanged old output is retained.
        if stage is final and run.status not in {"success", "waiting_review"}:
            continue
        if old and old.output_content == content(value):
            # Successful regeneration of identical content is still a successful attempt.
            if stage is current and active and run.status in {"success", "waiting_review"}:
                publish(active, stage, value)
            continue
        target = next(
            (
                a
                for a in attempts.values()
                if a.stage_id == stage.id
                and worker
                and a.worker_task_id == worker.task_id
                and a.status not in TERMINAL
            ),
            None,
        )
        if target is None:
            # Never overwrite an older success when an edit is saved during review.
            target = new_attempt(
                session,
                stage,
                attempts,
                run,
                worker=worker
                if old is None
                and not any(
                    a.stage_id == stage.id and worker and a.worker_task_id == worker.task_id
                    for a in attempts.values()
                )
                else None,
                operation="edit" if old else "generate",
            )
        target.output_context_json = extra_config(config)
        publish(target, stage, value)
        target.finished_at = datetime.now(UTC)
        # Intermediate valid output can be persisted even when a later stage fails.
        if stage.stage_order < current.stage_order and not run.checkpoint_enabled:
            stage.review_status = "not_required"

    if active:
        if run.status not in {"failed", "error", "canceled"}:
            active.output_context_json = extra_config(config)
        active.progress_json = deepcopy(run.result_summary_json)
        active.error_message = run.error_message or None
        active.remediation = run.remediation or None
        if run.status in TERMINAL or run.status == "waiting_review":
            active.status = "success" if run.status in {"success", "waiting_review"} else run.status
            active.finished_at = (
                (worker.finished_at if worker else None) or run.finished_at or datetime.now(UTC)
            )
            current.execution_status = "success" if active.status == "success" else "failed"
            current.active_attempt_id = None
        elif active.status == "success":
            current.execution_status = "success"
            current.active_attempt_id = None
        else:
            current.execution_status = (
                "running" if run.status in {"running", "claimed"} else "pending"
            )
    if run.status == "waiting_review":
        current.review_status = "pending"
    if run.review_status in {"approved", "rejected"}:
        final.review_status = run.review_status
        final.reviewer_user_id = run.reviewer_user_id or None
        final.reviewed_at = run.reviewed_at
        final.review_comment = run.review_comment or None
    session.flush()
    if run.import_status == "imported":
        record = session.scalar(select(Import).where(Import.run_id == run.run_id))
        if record is None:
            session.add(
                Import(
                    id=ident(),
                    run_id=run.run_id,
                    artifact_attempt_id=final.current_artifact_attempt_id,
                    imported_by=getattr(run, "_actor", None),
                    imported_at=run.imported_at,
                    imported_targets_json=deepcopy(run.imported_targets),
                    idempotency_key=f"run:{run.run_id}",
                )
            )
    for key in ("_operation", "_stage_review", "_worker_event"):
        run.__dict__.pop(key, None)


def state(run):
    return deepcopy(
        {
            field: getattr(run, field, None)
            for field in (
                "status",
                "current_stage",
                "stage_status",
                "config_json",
                "result_yaml",
                "result_summary_json",
                "error_message",
                "remediation",
                "review_status",
                "reviewer_user_id",
                "reviewed_at",
                "review_comment",
                "import_status",
                "imported_at",
                "imported_targets",
                "started_at",
                "finished_at",
            )
        }
    )


def persist(session: Session):
    """Synchronize observed AI runs and enqueue rows in the caller's transaction."""
    # SQLAlchemy keeps only weak references after flush. Keep new queue objects
    # alive until their transient model connection is frozen in the attempt.
    queued_workers = [row for row in session.new if isinstance(row, WorkerTask)]
    runs = [
        r
        for r in list(session.identity_map.values()) + list(session.new)
        if isinstance(r, AiGenerateTaskRun)
        and (
            getattr(r, "_execution_state", None) != state(r)
            or any(
                getattr(r, key, None) for key in ("_operation", "_stage_review", "_worker_event")
            )
        )
    ]
    session.flush()
    for run in runs:
        if run not in session.deleted:
            sync_run(session, run)
            project(session, run)
            run._execution_state = state(run)
    session.flush()
    queued_workers.clear()


def project(session, run):
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


def _project(run, stages, attempts, imported):
    if not stages:
        raise ErrNotFound
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
        artifact = attempts.get(stage.current_artifact_attempt_id)
        if artifact is None or artifact.stage_id != stage.id:
            continue
        value = artifact.output_content
        if stage.stage in FIELDS:
            if artifact.output_format == "json":
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
        for field, value in (
            ("review_status", final.review_status),
            ("reviewer_user_id", final.reviewer_user_id or ""),
            ("reviewed_at", final.reviewed_at),
            ("review_comment", final.review_comment or ""),
        ):
            setattr(run, field, value)
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
    run._execution_state = state(run)
    return run


def require_current_worker(session, run, task):
    """The run row must be locked before checking and applying a worker event."""
    latest = session.scalar(
        select(WorkerTask.task_id)
        .where(WorkerTask.domain == "ai", WorkerTask.run_id == run.run_id)
        .order_by(WorkerTask.created_at.desc(), WorkerTask.id.desc())
    )
    if latest != task.task_id or task.status in TERMINAL:
        raise ErrBadRequest
    stages, attempts = graph(session, run)
    active = [attempts[s.active_attempt_id] for s in stages if s.active_attempt_id in attempts]
    if active and not any(a.worker_task_id == task.task_id for a in active):
        raise ErrBadRequest


def worker_input(session, run, task):
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


def project_many(session, runs):
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
    grouped = {run_id: [] for run_id in ids}
    for stage in stages:
        grouped[stage.run_id].append(stage)
    return [_project(run, grouped[run.run_id], attempts, imports.get(run.run_id)) for run in runs]


def apply_scope(run, scope):
    if scope is None:
        raise ErrNotFound
    run.project_id, run.sprint_id, run.requirement_id = scope
    run.trigger_type = "manual"  # retained only as a legacy wire default
