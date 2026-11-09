"""Stable-stage lookup for single-stage auxiliary AI tasks."""

from uuid import uuid4

from sqlalchemy import RowMapping, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest
from testing_agent.db.savepoint import ensure_outer_transaction
from testing_agent.domain.ai_tasks import AUXILIARY_EXECUTION_TYPES
from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage


async def lock_or_create_stage(session: AsyncSession, task_id: str) -> AiGenerationStage:
    """Find or create the task's stable stage while its task row is already locked."""
    await session.run_sync(ensure_outer_transaction)
    try:
        async with session.begin_nested():
            stage = AiGenerationStage(
                id=str(uuid4()), task_id=task_id, stage="generate", review_status="not_required"
            )
            session.add(stage)
            await session.flush()
        return stage
    except IntegrityError:
        existing = await session.scalar(
            select(AiGenerationStage)
            .where(AiGenerationStage.task_id == task_id, AiGenerationStage.stage == "generate")
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if existing is None:
            raise
        return existing


def _ranked_attempts(task_id: str):
    """Select summaries only, choosing the newest attempt in each execution."""
    return (
        select(
            AiExecution.execution_id,
            AiExecution.task_id,
            AiExecution.requested_by,
            AiExecution.created_at,
            AiGenerateTask.project_id,
            AiGenerateTask.sprint_id,
            AiGenerateTask.requirement_id,
            AiGenerateTask.task_type,
            AiGenerationAttempt.status,
            AiGenerationAttempt.started_at,
            AiGenerationAttempt.finished_at,
            AiGenerationAttempt.error_message,
            func.coalesce(func.length(AiGenerationAttempt.output_content), 0).label(
                "output_length"
            ),
            AiGenerationAttempt.input_snapshot_json["triggerType"]
            .as_string()
            .label("trigger_type"),
            func.row_number()
            .over(
                partition_by=AiExecution.execution_id,
                order_by=(AiGenerationAttempt.attempt_no.desc(), AiGenerationAttempt.id.desc()),
            )
            .label("rank"),
        )
        .join(AiGenerateTask, AiGenerateTask.task_id == AiExecution.task_id)
        .join(AiGenerationStage, AiGenerationStage.task_id == AiGenerateTask.task_id)
        .join(
            AiGenerationAttempt,
            (AiGenerationAttempt.stage_id == AiGenerationStage.id)
            & (AiGenerationAttempt.execution_id == AiExecution.execution_id),
        )
        .where(
            AiExecution.task_id == task_id,
            AiGenerationStage.stage == "generate",
            AiGenerateTask.task_type.in_(AUXILIARY_EXECUTION_TYPES),
        )
        .subquery()
    )


def _ranked_project_attempts(project_id: str, task_type: str):
    """Newest attempt of the newest execution for every auxiliary task in a project.

    Window ranking keeps the batch read bounded to one row per task even when the
    project accumulated many executions. Attempt rank picks the newest attempt in
    an execution; task rank picks the newest execution for the task.
    """
    return (
        select(
            AiExecution.execution_id,
            AiExecution.task_id,
            AiExecution.requested_by,
            AiExecution.created_at,
            AiGenerateTask.project_id,
            AiGenerateTask.sprint_id,
            AiGenerateTask.requirement_id,
            AiGenerateTask.task_type,
            AiGenerationAttempt.status,
            AiGenerationAttempt.started_at,
            AiGenerationAttempt.finished_at,
            AiGenerationAttempt.error_message,
            func.coalesce(func.length(AiGenerationAttempt.output_content), 0).label(
                "output_length"
            ),
            AiGenerationAttempt.input_snapshot_json["triggerType"]
            .as_string()
            .label("trigger_type"),
            func.row_number()
            .over(
                partition_by=AiExecution.execution_id,
                order_by=(AiGenerationAttempt.attempt_no.desc(), AiGenerationAttempt.id.desc()),
            )
            .label("attempt_rank"),
            func.row_number()
            .over(
                partition_by=AiGenerateTask.task_id,
                order_by=(
                    AiExecution.created_at.desc(),
                    AiExecution.execution_id.desc(),
                    AiGenerationAttempt.attempt_no.desc(),
                    AiGenerationAttempt.id.desc(),
                ),
            )
            .label("task_rank"),
        )
        .join(AiGenerateTask, AiGenerateTask.task_id == AiExecution.task_id)
        .join(AiGenerationStage, AiGenerationStage.task_id == AiGenerateTask.task_id)
        .join(
            AiGenerationAttempt,
            (AiGenerationAttempt.stage_id == AiGenerationStage.id)
            & (AiGenerationAttempt.execution_id == AiExecution.execution_id),
        )
        .where(
            AiGenerateTask.project_id == project_id,
            AiGenerationStage.stage == "generate",
            AiGenerateTask.task_type == task_type,
        )
        .subquery()
    )


async def latest_rows_for_project(
    session: AsyncSession, project_id: str, task_type: str
) -> list[RowMapping]:
    ranked = _ranked_project_attempts(project_id, task_type)
    return list(
        (
            await session.execute(
                select(ranked).where(
                    ranked.c.attempt_rank == 1,
                    ranked.c.task_rank == 1,
                )
            )
        )
        .mappings()
        .all()
    )


async def history_rows(
    session: AsyncSession, task_id: str, page: int, page_size: int
) -> tuple[list, dict[str, int], object | None]:
    """Read a bounded page, status counts and latest summary without large payloads."""
    if page < 1 or not 1 <= page_size <= 100:
        raise ErrBadRequest()
    ranked = _ranked_attempts(task_id)
    base = select(ranked).where(ranked.c.rank == 1)
    ordering = (ranked.c.created_at.desc(), ranked.c.execution_id.desc())
    rows = (
        (
            await session.execute(
                base.order_by(*ordering).offset((page - 1) * page_size).limit(page_size)
            )
        )
        .mappings()
        .all()
    )
    counts = {
        str(status): int(count)
        for status, count in (
            await session.execute(
                select(ranked.c.status, func.count())
                .where(ranked.c.rank == 1)
                .group_by(ranked.c.status)
            )
        ).all()
    }
    if page == 1:
        latest = rows[0] if rows else None
    else:
        latest = (await session.execute(base.order_by(*ordering).limit(1))).mappings().first()
    return list(rows), counts, latest


async def detail_row(session: AsyncSession, execution_id: str):
    """Load one execution, its owning task and most recent auxiliary attempt."""
    return (
        await session.execute(
            select(AiExecution, AiGenerateTask, AiGenerationAttempt)
            .join(AiGenerateTask, AiGenerateTask.task_id == AiExecution.task_id)
            .join(AiGenerationStage, AiGenerationStage.task_id == AiGenerateTask.task_id)
            .join(
                AiGenerationAttempt,
                (AiGenerationAttempt.stage_id == AiGenerationStage.id)
                & (AiGenerationAttempt.execution_id == AiExecution.execution_id),
            )
            .where(
                AiExecution.execution_id == execution_id,
                AiGenerationStage.stage == "generate",
                AiGenerateTask.task_type.in_(AUXILIARY_EXECUTION_TYPES),
            )
            .order_by(AiGenerationAttempt.attempt_no.desc(), AiGenerationAttempt.id.desc())
            .limit(1)
        )
    ).first()
