"""Execution-scoped state transitions for independent AI Worker dispatches.

The caller locks and validates the Worker queue row and lease, authorizes the
actor, validates artifacts, and commits the event as one transaction. Stable
stages allocate attempt numbers only; they never own another execution's state.
"""

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest
from testing_agent.domain.ai_execution_format import NO_REVIEW_STAGES, final_review_stage
from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.standalone_execution import lock_or_create_stage
from testing_agent.services.standalone_execution import workflow_stage_names


class StandaloneWorkerTransitions:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def current(
        self, task: AiGenerateTask, queue: WorkerTask
    ) -> tuple[AiExecution, AiGenerationStage, AiGenerationAttempt]:
        """Lock execution then stage and verify the queue still owns its active attempt."""
        root = await self.session.scalar(
            select(AiGenerationAttempt)
            .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
            .where(
                AiGenerationStage.task_id == task.task_id,
                AiGenerationAttempt.id == queue.run_id,
                AiGenerationAttempt.worker_task_id == queue.task_id,
            )
        )
        if (
            queue.domain != "ai"
            or queue.task_type != task.task_type
            or queue.status not in {"pending", "claimed", "running"}
            or task.requirement_id
            or root is None
        ):
            raise ErrBadRequest()
        execution = await self.session.scalar(
            select(AiExecution)
            .where(
                AiExecution.execution_id == root.execution_id, AiExecution.task_id == task.task_id
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if execution is None or execution.workflow_status not in {"pending", "claimed", "running"}:
            raise ErrBadRequest()
        stage = await self.session.scalar(
            select(AiGenerationStage)
            .where(
                AiGenerationStage.task_id == task.task_id,
                AiGenerationStage.stage == execution.current_stage,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if stage is None:
            raise ErrBadRequest()
        attempts = (
            await self.session.scalars(
                select(AiGenerationAttempt)
                .where(
                    AiGenerationAttempt.execution_id == execution.execution_id,
                    AiGenerationAttempt.stage_id == stage.id,
                    AiGenerationAttempt.worker_task_id == queue.task_id,
                    AiGenerationAttempt.status.in_({"pending", "claimed", "running"}),
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
        if len(attempts) != 1:
            raise ErrBadRequest()
        attempt = attempts[0]
        if attempt.requested_by != root.requested_by or (attempt.input_snapshot_json or {}).get(
            "llmConnectionId"
        ) != (root.input_snapshot_json or {}).get("llmConnectionId"):
            raise ErrBadRequest()
        return execution, stage, attempt

    async def claimed(self, task: AiGenerateTask, queue: WorkerTask) -> None:
        execution, _, attempt = await self.current(task, queue)
        if execution.workflow_status != "pending" or attempt.status != "pending":
            raise ErrBadRequest()
        execution.workflow_status = attempt.status = "claimed"
        await self.session.flush()

    async def started(self, task: AiGenerateTask, queue: WorkerTask) -> None:
        execution, _, attempt = await self.current(task, queue)
        if execution.workflow_status not in {"claimed", "running"}:
            raise ErrBadRequest()
        now = datetime.now(UTC)
        execution.workflow_status = attempt.status = "running"
        execution.started_at = execution.started_at or now
        attempt.started_at = attempt.started_at or now
        await self.session.flush()

    async def completed(
        self,
        task: AiGenerateTask,
        queue: WorkerTask,
        *,
        content: str,
        output_format: str,
        output_context: dict[str, Any] | None = None,
    ) -> None:
        """Finish a checked stage candidate and stop at its checkpoint or final result."""
        execution, stage, attempt = await self.current(task, queue)
        names = workflow_stage_names(task.task_type, execution.source_snapshot_json or {})
        final = final_review_stage(task.task_type, names)
        if (
            stage.stage not in names
            or attempt.status != "running"
            or not content
            or (
                not execution.checkpoint_enabled
                and stage.stage != final
                and stage.stage not in NO_REVIEW_STAGES
            )
        ):
            raise ErrBadRequest()
        now = datetime.now(UTC)
        attempt.status = "success"
        attempt.output_content = content
        attempt.output_format = output_format
        attempt.output_context_json = deepcopy(output_context)
        attempt.finished_at = now
        finished = stage.stage == final or stage.stage in NO_REVIEW_STAGES
        execution.workflow_status = "success" if finished else "waiting_review"
        execution.current_stage = "completed" if finished else stage.stage
        execution.finished_at = now if finished else None
        await self.session.flush()

    async def failed(
        self, task: AiGenerateTask, queue: WorkerTask, *, status: str, error_message: str
    ) -> None:
        if status not in {"failed", "error", "canceled"}:
            raise ErrBadRequest()
        execution, _, attempt = await self.current(task, queue)
        now = datetime.now(UTC)
        attempt.status = execution.workflow_status = status
        attempt.error_message = error_message
        attempt.finished_at = execution.finished_at = now
        await self.session.flush()

    async def advance(
        self,
        task: AiGenerateTask,
        queue: WorkerTask,
        *,
        next_stage: str,
        content: str,
        output_format: str,
        next_config: dict[str, Any],
    ) -> AiGenerationAttempt:
        """Persist an intermediate artifact and advance the same continuous dispatch."""
        execution, stage, attempt = await self.current(task, queue)
        names = workflow_stage_names(task.task_type, execution.source_snapshot_json or {})
        final = final_review_stage(task.task_type, names)
        if (
            execution.checkpoint_enabled
            or attempt.status != "running"
            or not content
            or stage.stage == final
            or stage.stage not in names
            or names.index(stage.stage) + 1 >= len(names)
            or names[names.index(stage.stage) + 1] != next_stage
            or next_stage in NO_REVIEW_STAGES
        ):
            raise ErrBadRequest()
        target, created_stage = await lock_or_create_stage(self.session, task.task_id, next_stage)
        highest = None
        if not created_stage:
            highest = await self.session.scalar(
                select(AiGenerationAttempt.attempt_no)
                .where(AiGenerationAttempt.stage_id == target.id)
                .order_by(AiGenerationAttempt.attempt_no.desc())
                .limit(1)
                .with_for_update()
            )
        now = datetime.now(UTC)
        attempt.status, attempt.output_content, attempt.output_format = (
            "success",
            content,
            output_format,
        )
        attempt.finished_at = now
        snapshot = deepcopy(attempt.input_snapshot_json or {})
        snapshot["config"] = deepcopy(next_config)
        snapshot["currentOutput"] = content
        following = AiGenerationAttempt(
            id=str(uuid4()),
            stage_id=target.id,
            execution_id=execution.execution_id,
            attempt_no=(highest or 0) + 1,
            operation="generate",
            worker_task_id=queue.task_id,
            requested_by=attempt.requested_by,
            input_snapshot_json=snapshot,
            status="running",
            review_status="pending" if next_stage == final else "not_required",
            invalidated_reason="",
            started_at=now,
        )
        self.session.add(following)
        execution.current_stage = next_stage
        await self.session.flush()
        return following
