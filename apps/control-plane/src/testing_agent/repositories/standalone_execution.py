"""Read independent workflow state and its execution-owned stage attempts."""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage


async def workflow_records(session: AsyncSession, execution_id: str):
    """Load one execution and its attempts in two bounded queries."""
    row = (
        await session.execute(
            select(AiExecution, AiGenerateTask)
            .join(AiGenerateTask, AiGenerateTask.task_id == AiExecution.task_id)
            .where(
                AiExecution.execution_id == execution_id,
                AiExecution.workflow_status.is_not(None),
                AiGenerateTask.requirement_id == "",
            )
        )
    ).one_or_none()
    if row is None:
        return None
    execution, task = row
    attempts = (
        await session.execute(
            select(AiGenerationStage.stage, AiGenerationAttempt)
            .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
            .where(
                AiGenerationAttempt.execution_id == execution_id,
                AiGenerationStage.task_id == task.task_id,
            )
            .order_by(AiGenerationAttempt.attempt_no, AiGenerationAttempt.id)
        )
    ).all()
    return execution, task, attempts


async def lock_or_create_stage(
    session: AsyncSession, task_id: str, stage_name: str
) -> tuple[AiGenerationStage, bool]:
    """Lock an existing stage or insert it without locking a missing index key.

    The unique (task_id, stage) constraint arbitrates concurrent creation. The
    savepoint lets a loser read the winner without rolling back its caller.
    """
    stage = await session.scalar(
        select(AiGenerationStage).where(
            AiGenerationStage.task_id == task_id, AiGenerationStage.stage == stage_name
        )
    )
    if stage is None:
        candidate = AiGenerationStage(id=str(uuid4()), task_id=task_id, stage=stage_name)
        try:
            async with session.begin_nested():
                session.add(candidate)
                await session.flush()
            return candidate, True
        except IntegrityError:
            stage = await session.scalar(
                select(AiGenerationStage)
                .where(AiGenerationStage.task_id == task_id, AiGenerationStage.stage == stage_name)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if stage is None:
                raise
            return stage, False
    locked = await session.scalar(
        select(AiGenerationStage)
        .where(AiGenerationStage.id == stage.id, AiGenerationStage.task_id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked is None:
        from testing_agent.core.errors import ErrBadRequest

        raise ErrBadRequest()
    return locked, False


async def workflow_task_id(session: AsyncSession, execution_id: str) -> str | None:
    """Resolve an independent execution's task before loading its private artifacts."""
    return await session.scalar(
        select(AiExecution.task_id).where(
            AiExecution.execution_id == execution_id,
            AiExecution.workflow_status.is_not(None),
        )
    )


async def dispatch_replay_records(session: AsyncSession, request_id: str):
    """Resolve a dispatch using current reads after locking its parent execution.

    A concurrent request may have created its REPEATABLE READ snapshot before
    the winning dispatch committed. Locking reads see that commit. The Worker
    locks the queue before the execution, so never wait on its queue lock while
    already holding the execution lock: a busy row is left for a later retry.
    """
    from testing_agent.models.worker_task import WorkerTask

    row = (
        await session.execute(
            select(WorkerTask, AiGenerationAttempt, AiGenerationStage)
            .join(AiGenerationAttempt, AiGenerationAttempt.id == WorkerTask.run_id)
            .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
            .where(WorkerTask.domain == "ai", WorkerTask.task_id == request_id)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if row is None:
        # Distinguish an unused identity from a queue record owned by another ledger.
        exists = await session.scalar(
            select(WorkerTask.id).where(WorkerTask.domain == "ai", WorkerTask.task_id == request_id)
        )
        return (None, None) if exists is not None else None
    queue, attempt, target_stage = row
    predecessor_id = (attempt.input_snapshot_json or {}).get("baseAttemptId")
    previous = (
        await session.execute(
            select(AiGenerationAttempt, AiGenerationStage)
            .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
            .where(AiGenerationAttempt.id == predecessor_id)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    return (queue, attempt, target_stage), previous
