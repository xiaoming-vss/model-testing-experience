"""Identity and replay checks shared by no-review AI dispatch entry points."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.request_identity import request_signature as request_signature
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.worker_task import WorkerTask


def request_id(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 64:
        raise ErrBadRequest()
    return value.strip()


async def find_replay(
    session: AsyncSession,
    *,
    task: AiGenerateTask,
    actor_id: str,
    request_id: str,
    signature: str,
    current_read: bool = False,
    active_attempt_id: str | None = None,
) -> AiGenerationAttempt | None:
    """Match immutable request identity, then recheck the original actor's permissions."""
    queue_statement = (
        select(WorkerTask)
        .where(WorkerTask.domain == "ai", WorkerTask.task_id == request_id)
        .execution_options(populate_existing=True)
    )
    # Never lock a missing queue key: InnoDB gap locks would serialize or
    # deadlock unrelated task creation. A locked stage can expose an active
    # attempt even if this transaction's earlier snapshot missed its queue.
    queue = await session.scalar(queue_statement)
    if queue is None and current_read and active_attempt_id:
        try:
            active = await session.scalar(
                select(AiGenerationAttempt)
                .where(AiGenerationAttempt.id == active_attempt_id)
                .with_for_update(nowait=True)
                .execution_options(populate_existing=True)
            )
            if active is not None and active.worker_task_id == request_id:
                queue = await session.scalar(queue_statement.with_for_update(nowait=True))
        except OperationalError as exc:
            if (getattr(exc.orig, "args", ()) or (None,))[0] in {1205, 3572}:
                raise dynamic_error(ErrBadRequest, "任务正在处理中，请稍后重试") from exc
            raise
    if queue is None:
        return None
    if current_read:
        try:
            queue = await session.scalar(queue_statement.with_for_update(nowait=True))
        except OperationalError as exc:
            if (getattr(exc.orig, "args", ()) or (None,))[0] in {1205, 3572}:
                raise dynamic_error(ErrBadRequest, "任务正在处理中，请稍后重试") from exc
            raise
        if queue is None:
            return None
    attempt_statement = (
        select(AiGenerationAttempt)
        .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
        .where(
            AiGenerationAttempt.id == queue.run_id,
            AiGenerationAttempt.worker_task_id == request_id,
            AiGenerationStage.task_id == task.task_id,
            AiGenerationAttempt.requested_by == actor_id,
        )
        .execution_options(populate_existing=True)
    )
    if current_read:
        attempt_statement = attempt_statement.with_for_update(nowait=True)
    try:
        attempt = await session.scalar(attempt_statement)
    except OperationalError as exc:
        if (getattr(exc.orig, "args", ()) or (None,))[0] in {1205, 3572}:
            raise dynamic_error(ErrBadRequest, "任务正在处理中，请稍后重试") from exc
        raise
    if (
        attempt is None
        or queue.task_type != task.task_type
        or (attempt.input_snapshot_json or {}).get("requestSignature") != signature
    ):
        raise dynamic_error(ErrBadRequest, "请求标识已用于其他操作或输入，请重新提交")
    from testing_agent.services.stage_storage.authorization import authorize_worker_actor

    await authorize_worker_actor(session, task, attempt)
    return attempt
