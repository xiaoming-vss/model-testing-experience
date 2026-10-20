"""Transactional stage/attempt storage and the legacy wire projection.

Business commands explicitly persist their run before committing. Legacy
wire attributes are ordinary properties, not main-table columns. Queue rows,
stage pointers and imports commit together. No ORM global hooks.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from testing_agent.core.errors import ErrBadRequest, ErrNotFound
from testing_agent.domain.ai_execution_format import (
    FIELDS,
    NO_REVIEW_KINDS,
    NO_REVIEW_STAGES,
    TERMINAL,
    content,
    extra_config,
    final_review_stage,
    final_stage,
    layout,
    mapping,
    output_format,
)
from testing_agent.domain.ai_execution_intent import ExecutionIntent
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
from testing_agent.repositories.ai_execution import (
    graph as graph,
)
from testing_agent.repositories.ai_execution import (
    project as project,
)
from testing_agent.repositories.ai_execution import (
    project_many as project_many,
)
from testing_agent.repositories.ai_execution import (
    worker_input as worker_input,
)

# 派生产物不需要人工审核：功能链路的图谱阶段，以及整体就是派生产物的测试单图谱任务。


def ident() -> str:
    return str(uuid4())


def new_attempt(
    session: Session,
    stage: Stage,
    attempts: dict[str, Attempt],
    run: AiGenerateTaskRun,
    *,
    worker: WorkerTask | None = None,
    operation: str = "generate",
    actor_id: str | None = None,
) -> Attempt:
    siblings = [a for a in attempts.values() if a.stage_id == stage.id]
    snapshot: dict[str, Any] = {
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
        or actor_id
        or run.trigger_user_id,
        input_snapshot_json=snapshot,
        revision_instruction=instruction,
        status="pending",
        created_at=datetime.now(UTC),
    )
    session.add(attempt)
    attempts[attempt.id] = attempt
    return attempt


def ensure_stages(
    session: Session, run: AiGenerateTaskRun, kind: str
) -> tuple[list[Stage], dict[str, Attempt]]:
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


def publish(attempt: Attempt, stage: Stage, value: Any) -> None:
    attempt.output_content = content(value)
    attempt.output_format = output_format(attempt.output_content)
    attempt.status = "success"
    stage.current_artifact_attempt_id = attempt.id
    stage.execution_status = "success"
    if stage.active_attempt_id == attempt.id:
        stage.active_attempt_id = None


def sync_run(
    session: Session, run: AiGenerateTaskRun, intent: ExecutionIntent, worker: WorkerTask | None
) -> None:
    kind = session.scalar(
        select(AiGenerateTask.task_type).where(AiGenerateTask.task_id == run.task_id)
    )
    if kind is None:
        raise ErrNotFound()
    stages, attempts = ensure_stages(session, run, kind)
    by_name = {s.stage: s for s in stages}
    stage_by_id = {s.id: s for s in stages}
    final = final_stage(stages)
    current = by_name.get(
        run.current_stage, final if run.current_stage == "completed" else stages[0]
    )
    worker = worker or session.scalar(
        select(WorkerTask)
        .where(WorkerTask.domain == "ai", WorkerTask.run_id == run.run_id)
        .order_by(WorkerTask.created_at.desc(), WorkerTask.id.desc())
    )
    config = mapping(run.config_json)
    operation = intent.operation
    # One queue dispatch may span all stages when checkpoints are disabled.
    queued = worker is not None and (
        worker.status in {"pending", "claimed", "running"}
        or intent.worker_event_id == worker.task_id
    )
    if queued and worker is not None:
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
            if not intent.worker_event_id:
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
                actor_id=intent.actor_id,
                operation=operation
                or ("revise" if config.get("revisionInstruction") else "generate"),
            )
        current.active_attempt_id = match.id
        if match.status != "success":
            match.status = "running" if worker.status in {"claimed", "running"} else "pending"
        if match.started_at is None and worker.status in {"claimed", "running"}:
            match.started_at = worker.started_at or datetime.now(UTC)
    active = attempts.get(current.active_attempt_id or "")
    review = intent.review
    if review:
        reviewed_stage = by_name[review.stage]
        reviewed_stage.review_status = review.status
        reviewed_stage.reviewer_user_id = intent.actor_id
        reviewed_stage.reviewed_at = datetime.now(UTC)
        reviewed_stage.review_comment = review.comment

    for stage in stages:
        value = (
            run.result_yaml
            if stage is final
            else config.get(FIELDS[stage.stage])
            if stage.stage in FIELDS
            else None
        )
        if value is None or value == "":
            continue
        old = attempts.get(stage.current_artifact_attempt_id or "")
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
                actor_id=intent.actor_id,
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
    if intent.reset_requirement_review and kind == "requirement_analysis":
        final.review_status = "pending"
        final.reviewer_user_id = None
        final.reviewed_at = None
        final.review_comment = None
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
                    imported_at=run.imported_at,
                    imported_targets_json=deepcopy(run.imported_targets),
                )
            )


def persist_run(
    session: Session,
    run: AiGenerateTaskRun,
    *,
    intent: ExecutionIntent = ExecutionIntent(),
    worker: WorkerTask | None = None,
) -> None:
    """Apply exactly one declared execution change, preserving the caller's transaction.

    The caller retains and supplies a newly queued WorkerTask so its selected model
    is frozen into the attempt even after flush. No session-wide dirty/new scan.
    """
    session.flush()
    sync_run(session, run, intent, worker)
    project(session, run)
    session.flush()


def require_current_worker(session: Session, run: AiGenerateTaskRun, task: WorkerTask) -> None:
    """The run row must be locked before checking and applying a worker event."""
    latest = session.scalar(
        select(WorkerTask.task_id)
        .where(WorkerTask.domain == "ai", WorkerTask.run_id == run.run_id)
        .order_by(WorkerTask.created_at.desc(), WorkerTask.id.desc())
    )
    if latest != task.task_id or task.status in TERMINAL:
        raise ErrBadRequest()
    stages, attempts = graph(session, run)
    active = [attempts[s.active_attempt_id] for s in stages if s.active_attempt_id in attempts]
    if active and not any(a.worker_task_id == task.task_id for a in active):
        raise ErrBadRequest()
