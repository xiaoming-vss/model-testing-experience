"""Resolve a Worker's current attempt within one independent execution.

The queue references the dispatched attempt for its entire lease. A continuous
multi-stage Worker can later advance to another attempt in the same execution;
that must never allow it to address a different execution or dispatch.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrForbidden
from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.stage_storage.authorization import authorize_worker_actor


@dataclass(frozen=True)
class StandaloneWorkerAuthority:
    execution: AiExecution
    task: AiGenerateTask
    dispatched_attempt: AiGenerationAttempt
    current_attempt: AiGenerationAttempt
    current_stage: AiGenerationStage
    actor_id: str


async def authorize_standalone_worker(
    session: AsyncSession, queue: WorkerTask, *, pending: bool = False
) -> StandaloneWorkerAuthority:
    """Recheck queue identity, active attempt and dispatcher's current authority.

    This is a read-only permission check. The event handler must subsequently
    lock the queue and execution and recheck current state before mutating it.
    """
    allowed = {"pending", "claimed", "running"} if pending else {"claimed", "running"}
    if queue.domain != "ai" or queue.status not in allowed:
        raise ErrForbidden()
    root = (
        await session.execute(
            select(AiGenerationAttempt, AiExecution, AiGenerateTask)
            .join(AiExecution, AiExecution.execution_id == AiGenerationAttempt.execution_id)
            .join(AiGenerateTask, AiGenerateTask.task_id == AiExecution.task_id)
            .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
            .where(
                AiGenerationAttempt.id == queue.run_id,
                AiGenerationAttempt.worker_task_id == queue.task_id,
                AiGenerationStage.task_id == AiGenerateTask.task_id,
                AiGenerateTask.task_type == queue.task_type,
                AiGenerateTask.requirement_id == "",
                AiExecution.workflow_status.in_({"pending", "claimed", "running"}),
            )
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if root is None:
        raise ErrForbidden()
    dispatched, execution, task = root
    rows = (
        await session.execute(
            select(AiGenerationAttempt, AiGenerationStage)
            .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
            .where(
                AiGenerationAttempt.execution_id == execution.execution_id,
                AiGenerationAttempt.worker_task_id == queue.task_id,
                AiGenerationAttempt.status.in_({"pending", "claimed", "running"}),
                AiGenerationStage.task_id == task.task_id,
                AiGenerationStage.stage == execution.current_stage,
            )
            .limit(2)
            .execution_options(populate_existing=True)
        )
    ).all()
    if len(rows) != 1:
        raise ErrForbidden()
    current, stage = rows[0]
    root_snapshot = dispatched.input_snapshot_json or {}
    current_snapshot = current.input_snapshot_json or {}
    if current.requested_by != dispatched.requested_by or current_snapshot.get(
        "llmConnectionId"
    ) != root_snapshot.get("llmConnectionId"):
        raise ErrForbidden()
    actor = await authorize_worker_actor(session, task, dispatched)
    return StandaloneWorkerAuthority(execution, task, dispatched, current, stage, actor)
