"""Paginated independent execution history without loading artifact bodies."""

from typing import Any

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest
from testing_agent.models.ai_execution import AiExecution as Execution
from testing_agent.models.ai_generate_task import AiGenerateTask as Task
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport as Import
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt as Attempt
from testing_agent.models.ai_generation_stage import AiGenerationStage as Stage


def _last_attempt(stage_expr: Any, *, successful: bool = False):
    criteria = [
        Attempt.execution_id == Execution.execution_id,
        Stage.task_id == Task.task_id,
        Stage.stage == stage_expr,
    ]
    if successful:
        criteria.extend(
            [
                Attempt.status == "success",
                Attempt.output_content.is_not(None),
                Attempt.invalidated_at.is_(None),
            ]
        )
    return (
        select(Attempt.id)
        .join(Stage, Stage.id == Attempt.stage_id)
        .where(*criteria)
        .order_by(Attempt.attempt_no.desc(), Attempt.id.desc())
        .limit(1)
        .correlate(Execution, Task)
        .scalar_subquery()
    )


async def standalone_history_rows(
    session: AsyncSession,
    task_id: str,
    page: int,
    page_size: int,
    pipeline_filter: str,
) -> tuple[list[Any], dict[str, int], int, Any | None, list[Any], list[Any]]:
    """Return one page, counts, latest and batched artifact/source metadata."""
    if page < 1 or not 1 <= page_size <= 100:
        raise ErrBadRequest()
    if pipeline_filter not in {
        "all",
        "running",
        "review_pending",
        "approved",
        "import_pending",
        "imported",
        "rejected",
        "failed",
        "canceled",
    }:
        raise ErrBadRequest()
    final_stage = case(
        (Task.task_type == "functional_case_generate", "detailed_cases"),
        (Task.task_type == "ui_case_generate", "ui_yaml"),
        else_="generate",
    )
    current_stage = case(
        (Execution.current_stage == "completed", final_stage), else_=Execution.current_stage
    )
    final_id = _last_attempt(final_stage, successful=True)
    current_id = _last_attempt(current_stage)
    review = (
        select(Attempt.review_status)
        .where(Attempt.id == final_id)
        .correlate(Execution, Task)
        .scalar_subquery()
    )
    imported = (
        select(Import.id).where(Import.attempt_id == final_id).correlate(Execution, Task).exists()
    )
    active_final = (
        select(Attempt.id)
        .join(Stage, Stage.id == Attempt.stage_id)
        .where(
            Attempt.execution_id == Execution.execution_id,
            Stage.task_id == Task.task_id,
            Stage.stage == final_stage,
            Attempt.status.in_(["pending", "queued", "claimed", "running"]),
        )
        .correlate(Execution, Task)
        .exists()
    )
    status = Execution.workflow_status
    pending = func.coalesce(review, "pending")
    pipeline = case(
        (status.in_(["failed", "error"]), "failed"),
        (status == "canceled", "canceled"),
        (review == "rejected", "rejected"),
        (status == "waiting_review", "review_pending"),
        (
            # A running revision keeps the previous approved attempt as the
            # last successful one; the active attempt still means "running".
            (status.in_(["pending", "queued", "claimed", "running"]))
            & ((pending != "approved") | active_final),
            "running",
        ),
        ((review == "approved") & imported, "imported"),
        (review == "approved", "import_pending"),
        else_="review_pending",
    )
    base = [
        Execution.task_id == task_id,
        Execution.workflow_status.is_not(None),
        Task.requirement_id == "",
    ]
    criteria = [*base]
    if pipeline_filter != "all":
        criteria.append(
            review == "approved" if pipeline_filter == "approved" else pipeline == pipeline_filter
        )
    count_rows = (
        await session.execute(
            select(status, func.count())
            .select_from(Execution)
            .join(Task, Task.task_id == Execution.task_id)
            .where(*criteria)
            .group_by(status)
        )
    ).all()
    counts: dict[str, int] = {str(row[0]): int(row[1]) for row in count_rows}
    review_pending = await session.scalar(
        select(func.count())
        .select_from(Execution)
        .join(Task, Task.task_id == Execution.task_id)
        .where(
            *criteria,
            (status == "waiting_review")
            | ((status == "success") & (pending == "pending") & ~imported),
        )
    )
    current = Attempt.__table__.alias("history_current_attempt")
    final = Attempt.__table__.alias("history_final_attempt")
    statement = (
        select(
            Execution.execution_id,
            Execution.task_id,
            Execution.requested_by,
            Execution.workflow_status,
            Execution.current_stage,
            Execution.checkpoint_enabled,
            Execution.trigger_type,
            Execution.created_at,
            Execution.started_at,
            Execution.finished_at,
            Task.project_id,
            Task.sprint_id,
            Task.requirement_id,
            current.c.status.label("current_status"),
            current.c.error_message.label("current_error"),
            current.c.created_at.label("current_created"),
            final.c.id.label("final_attempt_id"),
            final.c.review_status,
            final.c.reviewer_user_id,
            final.c.reviewed_at,
            final.c.review_comment,
            (func.length(final.c.output_content) > 0).label("has_result"),
        )
        .select_from(Execution)
        .join(Task, Task.task_id == Execution.task_id)
        .outerjoin(
            current,
            and_(current.c.execution_id == Execution.execution_id, current.c.id == current_id),
        )
        .outerjoin(
            final, and_(final.c.execution_id == Execution.execution_id, final.c.id == final_id)
        )
    )

    def ordered(conditions: list[Any]):
        return statement.where(*conditions).order_by(
            Execution.created_at.desc(), Execution.execution_id.desc()
        )

    rows = (
        await session.execute(ordered(criteria).offset((page - 1) * page_size).limit(page_size))
    ).all()
    latest = (
        rows[0]
        if page == 1 and pipeline_filter == "all" and rows
        else (await session.execute(ordered(base).limit(1))).first()
    )
    unique = {row.execution_id: row for row in [*rows, *([latest] if latest else [])]}
    ids = list(unique)
    if not ids:
        return list(rows), counts, int(review_pending or 0), latest, [], []
    artifacts = (
        await session.execute(
            select(Attempt.execution_id, Stage.stage)
            .join(Stage, Stage.id == Attempt.stage_id)
            .where(
                Attempt.execution_id.in_(ids),
                Attempt.status == "success",
                Attempt.output_content.is_not(None),
                func.length(Attempt.output_content) > 0,
                Attempt.invalidated_at.is_(None),
                Stage.task_id == task_id,
            )
            .distinct()
        )
    ).all()
    final_ids = [row.final_attempt_id for row in unique.values() if row.final_attempt_id]
    imports = (
        (
            await session.execute(
                select(Import.attempt_id, Import.target_type, Import.target_id, Import.imported_at)
                .where(Import.attempt_id.in_(final_ids))
                .order_by(Import.imported_at, Import.id)
            )
        ).all()
        if final_ids
        else []
    )
    return list(rows), counts, int(review_pending or 0), latest, list(artifacts), list(imports)


async def has_standalone_history(session: AsyncSession, task_id: str) -> bool:
    """Choose the new ledger once this independent task has executions."""
    return bool(
        await session.scalar(
            select(Execution.execution_id)
            .where(Execution.task_id == task_id, Execution.workflow_status.is_not(None))
            .limit(1)
        )
    )
