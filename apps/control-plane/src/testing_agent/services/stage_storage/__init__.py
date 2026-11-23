"""direct stage persistence.

The caller holds the outer transaction and owns authorization, validation,
worker queue creation, input freezing and source locks.
"""

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest, ErrNotFound, dynamic_error
from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage


class DirectStageStorage:
    """Read and modify one stable stage using the caller's transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_stage(self, stage_id: str) -> AiGenerationStage:
        stage = await self.session.scalar(
            select(AiGenerationStage)
            .where(AiGenerationStage.id == stage_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if stage is None:
            raise ErrNotFound()
        return stage

    async def current(self, stage: AiGenerationStage) -> AiGenerationAttempt | None:
        if not stage.current_attempt_id:
            return None
        return await self.session.scalar(
            select(AiGenerationAttempt)
            .where(
                AiGenerationAttempt.id == stage.current_attempt_id,
                AiGenerationAttempt.stage_id == stage.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def _next_attempt_no(self, stage_id: str) -> int:
        maximum = await self.session.scalar(
            select(func.max(AiGenerationAttempt.attempt_no)).where(
                AiGenerationAttempt.stage_id == stage_id
            )
        )
        return (maximum or 0) + 1

    async def prepare(
        self,
        stage_id: str,
        *,
        worker_task_id: str,
        requested_by: str,
        input_snapshot: dict[str, Any],
        operation: str = "generate",
        expected_attempt_id: str | None = None,
        revision_instruction: str | None = None,
        revision_attachments: tuple[dict[str, str], ...] = (),
        attempt_id: str | None = None,
        execution_id: str | None = None,
        new_execution_id: str | None = None,
        review_required: bool = True,
        allow_multiple_candidates: bool = False,
    ) -> AiGenerationAttempt:
        """Reserve a generation attempt; caller enqueues its worker in this transaction."""
        stage = await self.lock_stage(stage_id)
        current = await self.current(stage)
        if stage.active_attempt_id:
            raise dynamic_error(ErrBadRequest, "阶段正在运行")
        draft_exists = bool(
            not allow_multiple_candidates
            and review_required
            and stage.review_status == "pending"
            and current is not None
            and current.status == "success"
            and current.output_content
            and current.invalidated_at is None
        )
        if (
            not worker_task_id
            or not requested_by
            or operation not in {"generate", "retry", "revise"}
        ):
            raise ErrBadRequest()
        snapshot = deepcopy(input_snapshot)
        if operation == "revise":
            candidate_revision = allow_multiple_candidates and (
                snapshot.get("candidateProtocol") == "single-current/2"
            )
            if not candidate_revision and current and isinstance(current.input_snapshot_json, dict):
                if current.input_snapshot_json.get("candidateProtocol") is not None:
                    raise dynamic_error(ErrBadRequest, "候选结果请使用候选派生流程修改")
            parent = snapshot.get("revisionParent")
            if (
                not candidate_revision
                or not isinstance(parent, dict)
                or not expected_attempt_id
                or parent.get("attemptId") != expected_attempt_id
                or not revision_instruction
                or not revision_instruction.strip()
                or snapshot.get("revisionInstruction") != revision_instruction
                or not attempt_id
                or snapshot.get("revisionAttemptId") != attempt_id
                or snapshot.get("revisionActorId") != requested_by
                or revision_attachments
            ):
                raise ErrBadRequest()
        elif draft_exists:
            raise dynamic_error(ErrBadRequest, "阶段已有待审核内容")
        if execution_id and new_execution_id:
            raise ErrBadRequest()
        if execution_id:
            execution = await self.session.scalar(
                select(AiExecution)
                .where(
                    AiExecution.execution_id == execution_id,
                    AiExecution.task_id == stage.task_id,
                )
                .with_for_update()
            )
            if execution is None or execution.workflow_status is not None:
                raise ErrBadRequest()
        else:
            execution = AiExecution(
                execution_id=new_execution_id or str(uuid4()),
                task_id=stage.task_id,
                requested_by=requested_by,
            )
            self.session.add(execution)
        attempt = AiGenerationAttempt(
            id=attempt_id or str(uuid4()),
            stage_id=stage.id,
            execution_id=execution.execution_id,
            attempt_no=await self._next_attempt_no(stage.id),
            operation=operation,
            worker_task_id=worker_task_id,
            requested_by=requested_by,
            input_snapshot_json=snapshot,
            revision_instruction=revision_instruction if operation == "revise" else None,
            status="pending",
            invalidated_reason="",
            created_at=datetime.now(UTC),
        )
        self.session.add(attempt)
        stage.active_attempt_id = attempt.id
        stage.review_status = "pending" if review_required else "not_required"
        await self.session.flush()
        return attempt

    async def publish(
        self,
        stage_id: str,
        *,
        attempt_id: str,
        worker_task_id: str,
        content: str,
        output_format: str,
        output_context: dict[str, Any] | None,
    ) -> AiGenerationAttempt:
        """Publish a verified worker result only for the currently active attempt."""
        stage = await self.lock_stage(stage_id)
        attempt = await self.session.scalar(
            select(AiGenerationAttempt)
            .where(AiGenerationAttempt.id == attempt_id, AiGenerationAttempt.stage_id == stage_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            attempt is None
            or stage.active_attempt_id != attempt_id
            or attempt.worker_task_id != worker_task_id
            or attempt.status not in {"pending", "claimed", "running"}
            or not content.strip()
        ):
            raise ErrBadRequest()
        attempt.output_content = content
        attempt.output_format = output_format
        attempt.output_context_json = deepcopy(output_context)
        attempt.status = "success"
        attempt.finished_at = datetime.now(UTC)
        stage.active_attempt_id = None
        stage.current_attempt_id = attempt.id
        if stage.review_status != "not_required":
            stage.review_status = "pending"
        await self.session.flush()
        return attempt
