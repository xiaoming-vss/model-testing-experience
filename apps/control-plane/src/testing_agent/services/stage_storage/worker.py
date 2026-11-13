"""stage-owned worker transitions.

Callers must authorize the actor, lock the WorkerTask first, check worker ID and
lease, validate returned artifacts and commit task plus stage in one transaction.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.services.stage_storage import DirectStageStorage
from testing_agent.services.stage_storage.module_progress import accept_module_progress


class StageWorkerTransitions:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.storage = DirectStageStorage(session)

    async def current(
        self, stage_id: str, attempt_id: str, worker_task_id: str
    ) -> tuple[AiGenerationStage, AiGenerationAttempt]:
        stage = await self.storage.lock_stage(stage_id)
        attempt = await self.session.scalar(
            select(AiGenerationAttempt)
            .where(AiGenerationAttempt.id == attempt_id, AiGenerationAttempt.stage_id == stage.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            attempt is None
            or stage.active_attempt_id != attempt.id
            or attempt.worker_task_id != worker_task_id
            or attempt.status not in {"pending", "claimed", "running"}
        ):
            raise ErrBadRequest()
        return stage, attempt

    async def started(self, stage_id: str, attempt_id: str, worker_task_id: str) -> None:
        _, attempt = await self.current(stage_id, attempt_id, worker_task_id)
        attempt.status = "running"
        attempt.started_at = attempt.started_at or datetime.now(UTC)
        await self.session.flush()

    async def progress(
        self, stage_id: str, attempt_id: str, worker_task_id: str, progress: dict[str, Any]
    ) -> None:
        stage, attempt = await self.current(stage_id, attempt_id, worker_task_id)
        if attempt.status != "running":
            raise ErrBadRequest()
        accept_module_progress(attempt, stage.stage, progress.get("summary"))
        await self.session.flush()

    async def completed(
        self,
        stage_id: str,
        attempt_id: str,
        worker_task_id: str,
        *,
        content: str,
        output_format: str,
        output_context: dict[str, Any] | None,
    ) -> AiGenerationAttempt:
        _, attempt = await self.current(stage_id, attempt_id, worker_task_id)
        previous = (attempt.output_context_json or {}).get("moduleGeneration")
        if previous is not None:
            output_context = {**(output_context or {}), "moduleGeneration": previous}
        return await self.storage.publish(
            stage_id,
            attempt_id=attempt_id,
            worker_task_id=worker_task_id,
            content=content,
            output_format=output_format,
            output_context=output_context,
        )

    async def failed(
        self,
        stage_id: str,
        attempt_id: str,
        worker_task_id: str,
        *,
        error_message: str,
        status: str = "failed",
    ) -> None:
        if status not in {"failed", "error", "canceled"}:
            raise ErrBadRequest()
        stage, attempt = await self.current(stage_id, attempt_id, worker_task_id)
        attempt.status = status
        attempt.error_message = error_message
        attempt.finished_at = datetime.now(UTC)
        stage.active_attempt_id = None
        # A failure never changes an existing approved version. Its error is
        # attached to this attempt for the stage view until the next dispatch.
        await self.session.flush()
