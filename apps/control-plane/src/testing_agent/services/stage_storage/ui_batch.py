"""UI source-batch transitions; caller owns task lock and transaction."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.worker_task import WorkerTask


async def detach_old_ui_batch(session: AsyncSession, task_id: str) -> None:
    """Invalidate unapproved old-batch work without modifying approved versions."""
    try:
        stages = list(
            (
                await session.scalars(
                    select(AiGenerationStage)
                    .where(
                        AiGenerationStage.task_id == task_id,
                        AiGenerationStage.stage.in_(("ui_surface", "ui_design", "ui_yaml")),
                    )
                    .order_by(AiGenerationStage.id)
                    .with_for_update(nowait=True)
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        versioned = set(
            (
                await session.scalars(
                    select(AiGenerateStageVersion.attempt_id).where(
                        AiGenerateStageVersion.task_id == task_id
                    )
                )
            ).all()
        )
        ids = {
            value
            for stage in stages
            for value in (stage.current_attempt_id, stage.active_attempt_id)
            if value
        }
        attempts = (
            list(
                (
                    await session.scalars(
                        select(AiGenerationAttempt)
                        .where(AiGenerationAttempt.id.in_(ids))
                        .order_by(AiGenerationAttempt.id)
                        .with_for_update(nowait=True)
                        .execution_options(populate_existing=True)
                    )
                ).all()
            )
            if ids
            else []
        )
        worker_ids = {
            attempt.worker_task_id
            for attempt in attempts
            if attempt.worker_task_id and attempt.status in {"pending", "claimed", "running"}
        }
        queues = (
            list(
                (
                    await session.scalars(
                        select(WorkerTask)
                        .where(WorkerTask.domain == "ai", WorkerTask.task_id.in_(worker_ids))
                        .order_by(WorkerTask.id)
                        .with_for_update(nowait=True)
                        .execution_options(populate_existing=True)
                    )
                ).all()
            )
            if worker_ids
            else []
        )
    except OperationalError as exc:
        if (getattr(exc.orig, "args", ()) or (None,))[0] in {1205, 3572}:
            raise dynamic_error(ErrBadRequest, "阶段仍在处理回传，请稍后更换输入") from exc
        raise
    by_id = {attempt.id: attempt for attempt in attempts}
    now = datetime.now(UTC)
    for stage in stages:
        for attempt_id in {stage.current_attempt_id, stage.active_attempt_id} - {None}:
            if attempt_id is None:
                continue
            attempt = by_id.get(attempt_id)
            if attempt is None or attempt.id in versioned:
                continue
            if attempt.invalidated_at is None:
                attempt.invalidated_at = now
                attempt.invalidated_reason = "生成输入已更换，请使用新一轮生成链"
            if attempt.status in {"pending", "claimed", "running"}:
                attempt.status = "canceled"
                attempt.finished_at = now
        if stage.current_attempt_id not in versioned:
            stage.current_attempt_id = None
        stage.active_attempt_id = None
        stage.review_status = "approved" if stage.current_attempt_id else "pending"
    for queue in queues:
        if queue.status in {"pending", "claimed", "running"}:
            queue.status = "canceled"
            queue.error_message = "生成输入已更换，本次执行已结束"
            queue.finished_at = now
            queue.lease_expires_at = now
    await session.flush()
