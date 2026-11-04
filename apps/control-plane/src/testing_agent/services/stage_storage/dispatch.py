"""transactional dispatch for a directly owned stage attempt.

The caller must lock and authorize the task, validate inputs, lock the selected
upstream versions, attach any revision files to the supplied attempt ID, then
commit this operation together with any UI source-batch changes.
"""

from copy import deepcopy
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest, ErrNotFound, dynamic_error
from testing_agent.db.savepoint import ensure_outer_transaction
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.stage_storage import DirectStageStorage


async def _lock_existing_worker(session: AsyncSession, statement) -> WorkerTask | None:
    try:
        return await session.scalar(statement.with_for_update(nowait=True))
    except OperationalError as exc:
        if (getattr(exc.orig, "args", ()) or (None,))[0] in {1205, 3572}:
            raise dynamic_error(ErrBadRequest, "任务正在处理中，请稍后重试") from exc
        raise


async def reserve_worker_identity(
    session: AsyncSession,
    task: AiGenerateTask,
    request_id: str,
    attempt_id: str | None = None,
) -> tuple[WorkerTask, bool]:
    """Reserve an invisible queue identity or lock an existing one without gap locks."""
    if not request_id:
        raise ErrBadRequest()
    queue_query = (
        select(WorkerTask)
        .where(WorkerTask.domain == "ai", WorkerTask.task_id == request_id)
        .execution_options(populate_existing=True)
    )
    # Probe without a lock so an absent identity cannot create a gap lock.
    # When the identity exists, fail fast if a Worker currently owns its lock.
    worker = await session.scalar(queue_query)
    reserved = None
    if worker is None:
        reserved = WorkerTask(
            domain="ai",
            task_id=request_id,
            task_type=task.task_type,
            run_id=attempt_id or str(uuid4()),
            status="pending",
        )
        try:
            async with session.begin_nested():
                session.add(reserved)
                await session.flush()
        except IntegrityError:
            worker = await _lock_existing_worker(session, queue_query)
            if worker is None:
                raise
        except OperationalError as exc:
            if (getattr(exc.orig, "args", ()) or (None,))[0] in {1205, 1213, 3572}:
                raise dynamic_error(ErrBadRequest, "任务正在处理中，请稍后重试") from exc
            raise
    else:
        worker = await _lock_existing_worker(session, queue_query)
        if worker is None:
            raise dynamic_error(ErrBadRequest, "任务正在处理中，请稍后重试")
    if worker is not None:
        return worker, True
    assert reserved is not None
    return reserved, False


async def replay_stage_attempt(
    session: AsyncSession,
    *,
    worker: WorkerTask,
    task: AiGenerateTask,
    stage_name: str,
    actor_id: str,
    operation: str,
    signature: str,
) -> AiGenerationAttempt:
    """Read a committed dispatch using current locks, without reconstructing inputs."""
    try:
        attempt = await session.scalar(
            select(AiGenerationAttempt)
            .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
            .where(
                AiGenerationAttempt.id == worker.run_id,
                AiGenerationAttempt.worker_task_id == worker.task_id,
                AiGenerationAttempt.requested_by == actor_id,
                AiGenerationAttempt.operation == operation,
                AiGenerationStage.task_id == task.task_id,
                AiGenerationStage.stage == stage_name,
            )
            .with_for_update(nowait=True)
            .execution_options(populate_existing=True)
        )
    except OperationalError as exc:
        if (getattr(exc.orig, "args", ()) or (None,))[0] in {1205, 3572}:
            raise dynamic_error(ErrBadRequest, "任务正在处理中，请稍后重试") from exc
        raise
    if (
        attempt is None
        or worker.task_type != task.task_type
        or (attempt.input_snapshot_json or {}).get("requestSignature") != signature
    ):
        raise dynamic_error(ErrBadRequest, "请求标识已用于其他阶段或输入，请重新提交")
    return attempt


async def _dispatch_stage_attempt(
    session: AsyncSession,
    *,
    task: AiGenerateTask,
    stage_id: str,
    request_id: str,
    actor_id: str,
    input_snapshot: dict[str, Any],
    operation: str = "generate",
    expected_attempt_id: str | None = None,
    revision_instruction: str | None = None,
    revision_attachments: tuple[dict[str, str], ...] = (),
    attempt_id: str | None = None,
    execution_id: str | None = None,
    new_execution_id: str | None = None,
    review_required: bool = True,
    reserved_worker: WorkerTask | None = None,
) -> tuple[AiGenerationAttempt, bool]:
    """Reserve one stage and enqueue once; return attempt and whether it was reused."""
    if not request_id or not actor_id or (execution_id and new_execution_id):
        raise ErrBadRequest()
    if reserved_worker is None:
        worker, replay = await reserve_worker_identity(session, task, request_id, attempt_id)
    else:
        worker, replay = reserved_worker, False
        if (
            worker.domain != "ai"
            or worker.task_id != request_id
            or worker.task_type != task.task_type
            or worker.status != "pending"
            or (attempt_id is not None and worker.run_id != attempt_id)
        ):
            raise ErrBadRequest()
    stage = await session.scalar(
        select(AiGenerationStage)
        .where(AiGenerationStage.id == stage_id, AiGenerationStage.task_id == task.task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if stage is None:
        raise ErrNotFound()
    if replay:
        try:
            attempt = await session.scalar(
                select(AiGenerationAttempt)
                .where(
                    AiGenerationAttempt.id == worker.run_id,
                    AiGenerationAttempt.worker_task_id == request_id,
                    AiGenerationAttempt.stage_id == stage.id,
                    AiGenerationAttempt.requested_by == actor_id,
                    AiGenerationAttempt.operation == operation,
                )
                .with_for_update(nowait=True)
                .execution_options(populate_existing=True)
            )
        except OperationalError as exc:
            if (getattr(exc.orig, "args", ()) or (None,))[0] in {1205, 3572}:
                raise dynamic_error(ErrBadRequest, "任务正在处理中，请稍后重试") from exc
            raise
        if (
            attempt is None
            or worker.task_type != task.task_type
            or (execution_id is not None and attempt.execution_id != execution_id)
            or (
                input_snapshot.get("requestSignature") is not None
                and (attempt.input_snapshot_json or {}).get("requestSignature")
                != input_snapshot["requestSignature"]
            )
        ):
            raise dynamic_error(ErrBadRequest, "请求标识已用于其他阶段或操作，请重新提交")
        return attempt, True
    attempt = await DirectStageStorage(session).prepare(
        stage.id,
        worker_task_id=request_id,
        requested_by=actor_id,
        input_snapshot=deepcopy(input_snapshot),
        operation=operation,
        expected_attempt_id=expected_attempt_id,
        revision_instruction=revision_instruction,
        revision_attachments=revision_attachments,
        attempt_id=worker.run_id,
        execution_id=execution_id,
        new_execution_id=new_execution_id,
        review_required=review_required,
    )
    worker.run_id = attempt.id
    await session.flush()
    return attempt, False


async def dispatch_stage_attempt(
    session: AsyncSession,
    *,
    task: AiGenerateTask,
    stage_id: str,
    request_id: str,
    actor_id: str,
    input_snapshot: dict[str, Any],
    operation: str = "generate",
    expected_attempt_id: str | None = None,
    revision_instruction: str | None = None,
    revision_attachments: tuple[dict[str, str], ...] = (),
    attempt_id: str | None = None,
    execution_id: str | None = None,
    new_execution_id: str | None = None,
    review_required: bool = True,
    reserved_worker: WorkerTask | None = None,
) -> tuple[AiGenerationAttempt, bool]:
    """Atomically reserve and enqueue, even when callers catch validation errors."""
    await session.run_sync(ensure_outer_transaction)
    async with session.begin_nested():
        return await _dispatch_stage_attempt(
            session,
            task=task,
            stage_id=stage_id,
            request_id=request_id,
            actor_id=actor_id,
            input_snapshot=input_snapshot,
            operation=operation,
            expected_attempt_id=expected_attempt_id,
            revision_instruction=revision_instruction,
            revision_attachments=revision_attachments,
            attempt_id=attempt_id,
            execution_id=execution_id,
            new_execution_id=new_execution_id,
            review_required=review_required,
            reserved_worker=reserved_worker,
        )
