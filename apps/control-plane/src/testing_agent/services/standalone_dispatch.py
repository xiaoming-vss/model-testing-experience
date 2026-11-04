"""Append a checkpoint continuation, retry or revision to one execution.

The caller validates business-specific artifacts and authorization, and owns
the transaction. Each dispatch has its own Worker/attempt identity, while the
public execution identity and prior attempts remain unchanged.
"""

import json
from copy import deepcopy
from hashlib import sha256
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.enums import RUN_ACTIVE_STATUSES
from testing_agent.core.errors import ErrBadRequest, ErrNotFound, dynamic_error
from testing_agent.domain.ai_execution_format import FIELDS, NO_REVIEW_STAGES, final_review_stage
from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.standalone_execution import lock_or_create_stage
from testing_agent.services.standalone_execution import workflow_stage_names


def _config_hash(config: dict[str, Any] | None) -> str:
    try:
        encoded = json.dumps(config, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ErrBadRequest() from exc
    return sha256(encoded.encode("utf-8")).hexdigest()


async def _enqueue_standalone_attempt(
    session: AsyncSession,
    *,
    task: AiGenerateTask,
    execution_id: str,
    request_id: str,
    actor_id: str,
    connection_id: str,
    stage_name: str,
    operation: str,
    expected_attempt_id: str,
    config: dict[str, Any] | None = None,
    revision_instruction: str | None = None,
    request_signature: str | None = None,
) -> tuple[AiGenerationAttempt, bool]:
    """Create a stage attempt without using the shared stage's candidate pointers."""
    if (
        task.requirement_id
        or not execution_id
        or not request_id
        or not actor_id
        or not connection_id
        or not expected_attempt_id
        or operation not in {"advance", "retry", "revise"}
        or (config is not None and not isinstance(config, dict))
    ):
        raise ErrBadRequest()
    # Reserve the unique queue key by inserting it instead of locking a missing
    # key: InnoDB gap locks on absent keys can deadlock unrelated executions.
    # The reservation is invisible until the caller commits this transaction.
    reserved = WorkerTask(
        domain="ai",
        task_id=request_id,
        task_type=task.task_type,
        run_id=execution_id,
        status="pending",
    )
    existing = None
    try:
        async with session.begin_nested():
            session.add(reserved)
            await session.flush()
    except IntegrityError:
        try:
            existing = await session.scalar(
                select(WorkerTask)
                .where(WorkerTask.domain == "ai", WorkerTask.task_id == request_id)
                .with_for_update(nowait=True)
                .execution_options(populate_existing=True)
            )
        except OperationalError as exc:
            if (getattr(exc.orig, "args", ()) or (None,))[0] in {1205, 3572}:
                raise dynamic_error(ErrBadRequest, "任务正在处理中，请稍后重试") from exc
            raise
        if existing is None:
            raise
    except OperationalError as exc:
        if (getattr(exc.orig, "args", ()) or (None,))[0] in {1205, 3572}:
            raise dynamic_error(ErrBadRequest, "任务正在处理中，请稍后重试") from exc
        raise
    if existing is not None:
        row = (
            await session.execute(
                select(AiGenerationAttempt, AiGenerationStage)
                .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
                .where(
                    AiGenerationAttempt.id == existing.run_id,
                    AiGenerationAttempt.worker_task_id == request_id,
                    AiGenerationAttempt.execution_id == execution_id,
                    AiGenerationStage.task_id == task.task_id,
                    AiGenerationStage.stage == stage_name,
                )
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if row is None:
            raise dynamic_error(ErrBadRequest, "请求标识已用于其他操作，请重新提交")
        attempt, _ = row
        snapshot = attempt.input_snapshot_json or {}
        if (
            existing.task_type != task.task_type
            or attempt.requested_by != actor_id
            or snapshot.get("dispatchOperation") != operation
            or snapshot.get("llmConnectionId") != connection_id
            or snapshot.get("baseAttemptId") != expected_attempt_id
            or snapshot.get("requestConfigHash") != _config_hash(config)
            or snapshot.get("requestSignature") != request_signature
            or (
                operation == "revise"
                and (attempt.revision_instruction or "") != (revision_instruction or "").strip()
            )
            or (operation != "revise" and bool((revision_instruction or "").strip()))
        ):
            raise dynamic_error(ErrBadRequest, "请求标识已用于其他操作，请重新提交")
        return attempt, True
    execution = await session.scalar(
        select(AiExecution)
        .where(AiExecution.execution_id == execution_id, AiExecution.task_id == task.task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if execution is None or execution.workflow_status is None:
        raise ErrNotFound()
    stages = workflow_stage_names(task.task_type, execution.source_snapshot_json or {})
    if stage_name not in stages:
        raise ErrBadRequest()
    current_stage = execution.current_stage or stages[0]
    if current_stage == "completed":
        current_stage = final_review_stage(task.task_type, stages)
    stage, created_stage = await lock_or_create_stage(session, task.task_id, stage_name)
    active = await session.scalar(
        select(AiGenerationAttempt.id)
        .where(
            AiGenerationAttempt.execution_id == execution_id,
            AiGenerationAttempt.status.in_(RUN_ACTIVE_STATUSES),
        )
        .limit(1)
        .with_for_update()
    )
    if active is not None:
        raise ErrBadRequest()
    base = (
        await session.execute(
            select(AiGenerationAttempt, AiGenerationStage)
            .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
            .where(
                AiGenerationAttempt.id == expected_attempt_id,
                AiGenerationAttempt.execution_id == execution_id,
                AiGenerationStage.task_id == task.task_id,
                AiGenerationStage.stage == current_stage,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if base is None:
        raise ErrBadRequest()
    previous, previous_stage = base
    latest = await session.scalar(
        select(AiGenerationAttempt.id)
        .where(
            AiGenerationAttempt.execution_id == execution_id,
            AiGenerationAttempt.stage_id == previous_stage.id,
        )
        .order_by(AiGenerationAttempt.attempt_no.desc(), AiGenerationAttempt.id.desc())
        .limit(1)
        .with_for_update()
    )
    if latest != previous.id:
        raise ErrBadRequest()
    own_config: dict[str, Any] = {}
    if config is not None:
        from testing_agent.services.standalone_execution_view import project_standalone_execution

        own_config = dict((await project_standalone_execution(session, execution_id)).config_json)
        own_field = FIELDS.get(stage_name) if operation == "revise" else None
        for field in set(FIELDS.values()) - {own_field}:
            if field in config and (field not in own_config or config[field] != own_config[field]):
                raise ErrBadRequest()
    instruction = (revision_instruction or "").strip()
    if operation == "retry":
        if (
            execution.workflow_status not in {"failed", "error"}
            or stage_name != current_stage
            or previous.status not in {"failed", "error"}
            or config is not None
            or instruction
        ):
            raise ErrBadRequest()
        snapshot = deepcopy(previous.input_snapshot_json or {})
        instruction = previous.revision_instruction or ""
    elif operation == "revise":
        if (
            execution.workflow_status not in {"waiting_review", "success"}
            or stage_name != current_stage
            or previous.status != "success"
            or previous.review_status != "pending"
            or not previous.output_content
            or not instruction
            or config is None
        ):
            raise ErrBadRequest()
        snapshot = deepcopy(previous.input_snapshot_json or {})
        own_config.pop("revisionInstruction", None)
        if "revisionAttachments" not in config:
            own_config.pop("revisionAttachments", None)
        snapshot["config"] = {**own_config, **deepcopy(config)}
        snapshot["currentOutput"] = previous.output_content
    else:
        index = stages.index(current_stage)
        if (
            stage_name != (stages[index + 1] if index + 1 < len(stages) else None)
            or execution.workflow_status not in {"waiting_review", "success"}
            or previous.status != "success"
            or previous.review_status != "approved"
            or config is None
            or instruction
        ):
            raise ErrBadRequest()
        own_config.pop("revisionInstruction", None)
        if "revisionAttachments" not in config:
            own_config.pop("revisionAttachments", None)
        if stage_name == "relation_analysis":
            if "resultYaml" in config and config["resultYaml"] != previous.output_content:
                raise ErrBadRequest()
            own_config["resultYaml"] = previous.output_content
        snapshot = {
            "source": deepcopy(execution.source_snapshot_json or {}),
            "config": {**own_config, **deepcopy(config)},
            "currentOutput": previous.output_content or "",
        }
    snapshot["llmConnectionId"] = connection_id
    snapshot["baseAttemptId"] = previous.id
    snapshot["dispatchOperation"] = operation
    snapshot["requestConfigHash"] = _config_hash(config)
    snapshot["requestSignature"] = request_signature
    highest = None
    if not created_stage:
        highest = await session.scalar(
            select(AiGenerationAttempt.attempt_no)
            .where(AiGenerationAttempt.stage_id == stage.id)
            .order_by(AiGenerationAttempt.attempt_no.desc())
            .limit(1)
            .with_for_update()
        )
    requires_review = stage_name not in NO_REVIEW_STAGES and (
        bool(execution.checkpoint_enabled)
        or stage_name == final_review_stage(task.task_type, stages)
    )
    attempt = AiGenerationAttempt(
        id=str(uuid4()),
        stage_id=stage.id,
        execution_id=execution_id,
        attempt_no=(highest or 0) + 1,
        operation="generate" if operation == "advance" else operation,
        worker_task_id=request_id,
        requested_by=actor_id,
        input_snapshot_json=snapshot,
        revision_instruction=instruction or None,
        status="pending",
        review_status="pending" if requires_review else "not_required",
        invalidated_reason="",
    )
    session.add(attempt)
    reserved.run_id = attempt.id
    execution.workflow_status = "pending"
    execution.current_stage = stage_name
    execution.finished_at = None
    await session.flush()
    return attempt, False


async def enqueue_standalone_attempt(
    session: AsyncSession,
    *,
    task: AiGenerateTask,
    execution_id: str,
    request_id: str,
    actor_id: str,
    connection_id: str,
    stage_name: str,
    operation: str,
    expected_attempt_id: str,
    config: dict[str, Any] | None = None,
    revision_instruction: str | None = None,
    request_signature: str | None = None,
) -> tuple[AiGenerationAttempt, bool]:
    """Atomically reserve and enqueue, including when callers catch validation errors."""
    async with session.begin_nested():
        return await _enqueue_standalone_attempt(
            session,
            task=task,
            execution_id=execution_id,
            request_id=request_id,
            actor_id=actor_id,
            connection_id=connection_id,
            stage_name=stage_name,
            operation=operation,
            expected_attempt_id=expected_attempt_id,
            config=config,
            revision_instruction=revision_instruction,
            request_signature=request_signature,
        )
