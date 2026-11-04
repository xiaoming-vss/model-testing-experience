"""Start independent generation workflows without sharing stage state across runs.

The caller locks and authorizes the task, freezes its input and owns the commit.
Worker queue identity is the initial attempt; the public run identity is the
execution. Stable stage rows only allocate attempt numbers and are never used as
the current-candidate pointer for independent runs.
"""

from copy import deepcopy
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.ai_execution_format import final_review_stage, layout
from testing_agent.domain.ui_generation_artifacts import UI_STAGES
from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.standalone_execution import lock_or_create_stage

_STANDALONE_TYPES = frozenset({"functional_case_generate", "api_case_generate", "ui_case_generate"})


def workflow_stage_names(task_type: str, source: dict[str, Any]) -> list[str]:
    """Return the existing stage order for an independent generation contract."""
    if task_type == "ui_case_generate":
        return list(UI_STAGES)
    if task_type == "api_case_generate" and source.get("apiWorkflowVersion") == "api_two_stage/1.0":
        return ["openapi_extract", "generate"]
    if task_type in _STANDALONE_TYPES:
        return layout(task_type)
    raise ErrBadRequest()


async def _start_standalone_execution(
    session: AsyncSession,
    *,
    task: AiGenerateTask,
    execution_id: str,
    request_id: str,
    actor_id: str,
    connection_id: str,
    source: dict[str, Any],
    config: dict[str, Any],
    checkpoint_enabled: bool,
    trigger_type: str = "manual",
) -> tuple[AiExecution, AiGenerationAttempt, bool]:
    """Reserve an execution, its initial stage attempt and queue row atomically.

    ``execution_id`` is a server-generated proposed ID. A matching request
    replay returns the previously committed execution ID instead.
    """
    if (
        task.task_type not in _STANDALONE_TYPES
        or task.requirement_id
        or not execution_id
        or not request_id
        or not actor_id
        or not connection_id
        or not isinstance(source, dict)
        or not isinstance(config, dict)
        or not trigger_type
    ):
        raise ErrBadRequest()
    frozen_source = deepcopy(source)
    for key, expected in (
        ("taskId", task.task_id),
        ("taskType", task.task_type),
        ("projectId", task.project_id),
        ("sprintId", task.sprint_id),
        ("requirementId", task.requirement_id),
        ("runId", execution_id),
    ):
        if key in frozen_source and frozen_source[key] != expected:
            raise ErrBadRequest()
    frozen_source["taskId"] = task.task_id
    frozen_source["runId"] = execution_id
    stages = workflow_stage_names(task.task_type, frozen_source)
    initial_stage = stages[0]
    # Reserve a unique request key with an insert. Locking a missing queue row
    # produces InnoDB gap locks that can deadlock unrelated executions.
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
                select(AiExecution, AiGenerationAttempt, AiGenerationStage)
                .join(
                    AiGenerationAttempt,
                    AiGenerationAttempt.execution_id == AiExecution.execution_id,
                )
                .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
                .where(
                    AiGenerationAttempt.id == existing.run_id,
                    AiGenerationAttempt.worker_task_id == request_id,
                    AiExecution.task_id == task.task_id,
                    AiGenerationStage.task_id == task.task_id,
                    AiGenerationStage.stage == initial_stage,
                )
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if row is None:
            raise dynamic_error(ErrBadRequest, "请求标识已用于其他操作，请重新提交")
        execution, attempt, _ = row
        previous = attempt.input_snapshot_json or {}
        prior_source = previous.get("source") or {}
        if not isinstance(prior_source, dict):
            raise ErrBadRequest()
        prior_source = dict(prior_source)
        requested_source = dict(frozen_source)
        prior_source.pop("runId", None)
        requested_source.pop("runId", None)
        if (
            existing.task_type != task.task_type
            or execution.workflow_status is None
            or execution.requested_by != actor_id
            or execution.checkpoint_enabled != checkpoint_enabled
            or execution.trigger_type != trigger_type
            or previous.get("llmConnectionId") != connection_id
            or previous.get("config") != config
            or prior_source != requested_source
        ):
            raise dynamic_error(ErrBadRequest, "请求标识已用于其他操作，请重新提交")
        return execution, attempt, True
    if await session.scalar(
        select(AiExecution.execution_id).where(AiExecution.execution_id == execution_id)
    ):
        raise dynamic_error(ErrBadRequest, "执行标识已存在，请重新提交")
    stage, created_stage = await lock_or_create_stage(session, task.task_id, initial_stage)
    previous_no = None
    if not created_stage:
        previous_no = await session.scalar(
            select(AiGenerationAttempt.attempt_no)
            .where(AiGenerationAttempt.stage_id == stage.id)
            .order_by(AiGenerationAttempt.attempt_no.desc())
            .limit(1)
            .with_for_update()
        )
    execution = AiExecution(
        execution_id=execution_id,
        task_id=task.task_id,
        requested_by=actor_id,
        workflow_status="pending",
        current_stage=initial_stage,
        checkpoint_enabled=checkpoint_enabled,
        trigger_type=trigger_type,
        source_snapshot_json=deepcopy(frozen_source),
    )
    attempt = AiGenerationAttempt(
        id=str(uuid4()),
        stage_id=stage.id,
        execution_id=execution_id,
        attempt_no=(previous_no or 0) + 1,
        operation="generate",
        worker_task_id=request_id,
        requested_by=actor_id,
        input_snapshot_json={
            "source": frozen_source,
            "config": deepcopy(config),
            "llmConnectionId": connection_id,
            "currentOutput": "",
        },
        status="pending",
        review_status=(
            "pending"
            if checkpoint_enabled or initial_stage == final_review_stage(task.task_type, stages)
            else "not_required"
        ),
        invalidated_reason="",
    )
    session.add(execution)
    await session.flush()
    session.add(attempt)
    reserved.run_id = attempt.id
    await session.flush()
    return execution, attempt, False


async def start_standalone_execution(
    session: AsyncSession,
    *,
    task: AiGenerateTask,
    execution_id: str,
    request_id: str,
    actor_id: str,
    connection_id: str,
    source: dict[str, Any],
    config: dict[str, Any],
    checkpoint_enabled: bool,
    trigger_type: str = "manual",
) -> tuple[AiExecution, AiGenerationAttempt, bool]:
    """Atomically reserve and create one execution or replay its request."""
    async with session.begin_nested():
        return await _start_standalone_execution(
            session,
            task=task,
            execution_id=execution_id,
            request_id=request_id,
            actor_id=actor_id,
            connection_id=connection_id,
            source=source,
            config=config,
            checkpoint_enabled=checkpoint_enabled,
            trigger_type=trigger_type,
        )
