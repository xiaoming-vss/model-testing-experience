"""Locking for the current attempt of an independent generation candidate.

The caller authorizes the action, checks import state and owns the commit.
No operation creates a Worker task or another execution.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.enums import RUN_ACTIVE_STATUSES
from testing_agent.core.errors import ErrBadRequest, ErrNotFound
from testing_agent.domain.ai_execution_format import final_review_stage
from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.services.standalone_execution import workflow_stage_names


async def lock_standalone_candidate(
    session: AsyncSession, *, task: AiGenerateTask, execution_id: str, stage_name: str
) -> tuple[AiExecution, AiGenerationStage, AiGenerationAttempt]:
    execution = await session.scalar(
        select(AiExecution)
        .where(AiExecution.execution_id == execution_id, AiExecution.task_id == task.task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if execution is None or execution.workflow_status is None or task.requirement_id:
        raise ErrNotFound()
    stages = workflow_stage_names(task.task_type, execution.source_snapshot_json or {})
    expected = execution.current_stage
    if expected == "completed":
        expected = final_review_stage(task.task_type, stages)
    if stage_name != expected or stage_name not in stages:
        raise ErrBadRequest()
    if execution.workflow_status not in {"success", "waiting_review"}:
        raise ErrBadRequest()
    stage = await session.scalar(
        select(AiGenerationStage)
        .where(AiGenerationStage.task_id == task.task_id, AiGenerationStage.stage == stage_name)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if stage is None:
        raise ErrNotFound()
    # The shared stage lock serializes sequence allocation before attempting a
    # current read of candidate rows; otherwise concurrent edits of different
    # runs can take incompatible empty-range locks before waiting on the stage.
    active = await session.scalar(
        select(AiGenerationAttempt.id)
        .where(
            AiGenerationAttempt.execution_id == execution_id,
            AiGenerationAttempt.status.in_(RUN_ACTIVE_STATUSES),
        )
        .with_hint(
            AiGenerationAttempt,
            "FORCE INDEX (idx_generation_attempt_execution_stage_no)",
            dialect_name="mysql",
        )
        .limit(1)
        .with_for_update()
    )
    if active is not None:
        raise ErrBadRequest()
    attempt = await session.scalar(
        select(AiGenerationAttempt)
        .where(
            AiGenerationAttempt.execution_id == execution_id,
            AiGenerationAttempt.stage_id == stage.id,
            AiGenerationAttempt.status == "success",
            AiGenerationAttempt.output_content.is_not(None),
            AiGenerationAttempt.invalidated_at.is_(None),
        )
        .order_by(AiGenerationAttempt.attempt_no.desc(), AiGenerationAttempt.id.desc())
        .limit(1)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if attempt is None or not attempt.output_content:
        raise ErrBadRequest()
    return execution, stage, attempt
