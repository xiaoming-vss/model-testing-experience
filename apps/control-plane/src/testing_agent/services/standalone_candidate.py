"""Execution-scoped edits and review for independent generation candidates.

The caller authorizes the action, validates the artifact, checks import state and
owns the commit.
No operation creates a Worker task or another execution. Checkpoint approval
and dispatch of the next stage must be committed in the same transaction.
"""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.enums import RUN_ACTIVE_STATUSES
from testing_agent.core.errors import ErrAiGenerateTaskRunReviewed, ErrBadRequest, ErrNotFound
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


async def save_standalone_draft(
    session: AsyncSession,
    *,
    task: AiGenerateTask,
    execution_id: str,
    stage_name: str,
    expected_attempt_id: str,
    actor_id: str,
    content: str,
    output_format: str,
) -> AiGenerationAttempt:
    """Create an edited attempt inside the same execution with no Worker dispatch."""
    if not actor_id or not content.strip() or output_format not in {"text", "json", "yaml"}:
        raise ErrBadRequest()
    _, stage, current = await lock_standalone_candidate(
        session, task=task, execution_id=execution_id, stage_name=stage_name
    )
    if current.id != expected_attempt_id or current.review_status != "pending":
        raise ErrBadRequest()
    highest = await session.scalar(
        select(AiGenerationAttempt.attempt_no)
        .where(AiGenerationAttempt.stage_id == stage.id)
        .order_by(AiGenerationAttempt.attempt_no.desc())
        .limit(1)
        .with_for_update()
    )
    snapshot = deepcopy(current.input_snapshot_json or {})
    snapshot["editBaseAttemptId"] = current.id
    edited = AiGenerationAttempt(
        id=str(uuid4()),
        stage_id=stage.id,
        execution_id=execution_id,
        attempt_no=(highest or 0) + 1,
        operation="edit",
        requested_by=actor_id,
        input_snapshot_json=snapshot,
        output_content=content,
        output_format=output_format,
        output_context_json=deepcopy(current.output_context_json),
        status="success",
        review_status="pending",
        invalidated_reason="",
        finished_at=datetime.now(UTC),
    )
    session.add(edited)
    await session.flush()
    return edited


async def review_standalone_candidate(
    session: AsyncSession,
    *,
    task: AiGenerateTask,
    execution_id: str,
    stage_name: str,
    expected_attempt_id: str,
    actor_id: str,
    approved: bool,
    comment: str,
) -> AiGenerationAttempt:
    """Review only the current candidate belonging to this particular execution."""
    if not actor_id:
        raise ErrBadRequest()
    execution, _, attempt = await lock_standalone_candidate(
        session, task=task, execution_id=execution_id, stage_name=stage_name
    )
    if attempt.id != expected_attempt_id:
        raise ErrBadRequest()
    if attempt.review_status != "pending":
        raise ErrAiGenerateTaskRunReviewed()
    attempt.review_status = "approved" if approved else "rejected"
    attempt.reviewer_user_id = actor_id
    attempt.reviewed_at = datetime.now(UTC)
    attempt.review_comment = comment
    if not approved and execution.workflow_status == "waiting_review":
        execution.workflow_status = "canceled"
        execution.finished_at = attempt.reviewed_at
    await session.flush()
    return attempt
