"""Delete one completed auxiliary execution without deleting business assets."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.enums import RUN_ACTIVE_STATUSES
from testing_agent.core.errors import ErrAiGenerateTaskRunRunning, ErrNotFound
from testing_agent.domain.ai_tasks import AUXILIARY_EXECUTION_TYPES
from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.worker_task import WorkerTask


async def delete_auxiliary_execution(
    session: AsyncSession, *, task_id: str, execution_id: str
) -> None:
    """Delete a terminal execution inside the caller's authorized task transaction.

    The caller locks the task and rechecks the owning business object and write
    permission first. Queue rows are locked before stages, matching Worker events.
    """
    task_type = await session.scalar(
        select(AiGenerateTask.task_type).where(AiGenerateTask.task_id == task_id).with_for_update()
    )
    if task_type not in AUXILIARY_EXECUTION_TYPES or task_type == "test_order_case_visualization":
        raise ErrNotFound()
    references = (
        await session.execute(
            select(
                AiGenerationAttempt.id,
                AiGenerationAttempt.stage_id,
                AiGenerationAttempt.worker_task_id,
            )
            .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
            .where(
                AiGenerationAttempt.execution_id == execution_id,
                AiGenerationStage.task_id == task_id,
            )
        )
    ).all()
    if not references:
        raise ErrNotFound()
    attempt_ids = [row.id for row in references]
    stage_ids = sorted({row.stage_id for row in references})
    worker_ids = [row.worker_task_id for row in references if row.worker_task_id]
    queues = list(
        (
            await session.scalars(
                select(WorkerTask)
                .where(
                    WorkerTask.domain == "ai",
                    WorkerTask.task_id.in_(worker_ids),
                    WorkerTask.run_id.in_(attempt_ids),
                )
                .order_by(WorkerTask.task_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    stages = list(
        (
            await session.scalars(
                select(AiGenerationStage)
                .where(AiGenerationStage.id.in_(stage_ids), AiGenerationStage.task_id == task_id)
                .order_by(AiGenerationStage.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    attempts = list(
        (
            await session.scalars(
                select(AiGenerationAttempt)
                .where(AiGenerationAttempt.id.in_(attempt_ids))
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    execution = await session.scalar(
        select(AiExecution)
        .where(AiExecution.execution_id == execution_id, AiExecution.task_id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if execution is None or len(attempts) != len(references):
        raise ErrNotFound()
    if (
        any(attempt.status in RUN_ACTIVE_STATUSES for attempt in attempts)
        or any(queue.status in RUN_ACTIVE_STATUSES for queue in queues)
        or any(stage.active_attempt_id in attempt_ids for stage in stages)
    ):
        raise ErrAiGenerateTaskRunRunning()
    for stage in stages:
        if stage.current_attempt_id in attempt_ids:
            previous = await session.scalar(
                select(AiGenerationAttempt.id)
                .where(
                    AiGenerationAttempt.stage_id == stage.id,
                    AiGenerationAttempt.id.not_in(attempt_ids),
                    AiGenerationAttempt.status == "success",
                    AiGenerationAttempt.invalidated_at.is_(None),
                    AiGenerationAttempt.output_content.is_not(None),
                )
                .order_by(AiGenerationAttempt.attempt_no.desc(), AiGenerationAttempt.id.desc())
                .limit(1)
            )
            stage.current_attempt_id = previous
    for queue in queues:
        await session.delete(queue)
    await session.delete(execution)
    await session.flush()
