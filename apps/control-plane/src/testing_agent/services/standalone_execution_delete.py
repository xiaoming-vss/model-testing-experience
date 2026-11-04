"""Delete a terminal independent execution while retaining formal assets and files."""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.enums import RUN_ACTIVE_STATUSES
from testing_agent.core.errors import ErrAiGenerateTaskRunRunning, ErrBadRequest, ErrNotFound
from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.models.worker_task import WorkerTask


async def delete_standalone_execution(
    session: AsyncSession, *, task_id: str, execution_id: str
) -> None:
    """Delete after task authorization and locking; caller owns the transaction."""
    references = (
        await session.execute(
            select(AiGenerationAttempt.id, AiGenerationAttempt.worker_task_id)
            .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
            .where(
                AiGenerationAttempt.execution_id == execution_id,
                AiGenerationStage.task_id == task_id,
            )
        )
    ).all()
    if not references:
        raise ErrNotFound()
    attempt_ids = {row.id for row in references}
    worker_ids = {row.worker_task_id for row in references if row.worker_task_id}
    # Worker callbacks lock their queue row before execution. Keep that order.
    queues = list(
        (
            await session.scalars(
                select(WorkerTask)
                .where(WorkerTask.domain == "ai", WorkerTask.task_id.in_(worker_ids))
                .order_by(WorkerTask.task_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    if any(queue.run_id not in attempt_ids for queue in queues):
        raise ErrBadRequest()
    execution = await session.scalar(
        select(AiExecution)
        .where(AiExecution.execution_id == execution_id, AiExecution.task_id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if execution is None or execution.workflow_status is None:
        raise ErrNotFound()
    attempts = list(
        (
            await session.scalars(
                select(AiGenerationAttempt)
                .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
                .where(
                    AiGenerationAttempt.execution_id == execution_id,
                    AiGenerationStage.task_id == task_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    if {attempt.id for attempt in attempts} != attempt_ids:
        # A concurrent Worker changed the run between discovery and the locks.
        raise ErrAiGenerateTaskRunRunning()
    if (
        execution.workflow_status in RUN_ACTIVE_STATUSES
        or any(attempt.status in RUN_ACTIVE_STATUSES for attempt in attempts)
        or any(queue.status in RUN_ACTIVE_STATUSES for queue in queues)
    ):
        raise ErrAiGenerateTaskRunRunning()
    import_ids = list(
        (
            await session.scalars(
                select(AiGenerateVersionImport.import_id)
                .where(AiGenerateVersionImport.attempt_id.in_(attempt_ids))
                .with_for_update()
            )
        ).all()
    )
    if import_ids:
        for target in (FunctionTestSuite, ApiCollection, UiTestSuite):
            await session.execute(
                update(target)
                .where(target.effective_import_id.in_(import_ids))
                .values(effective_import_id=None)
            )
    for queue in queues:
        await session.delete(queue)
    await session.delete(execution)
    await session.flush()
