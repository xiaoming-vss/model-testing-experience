"""Dispatch a no-review AI task using the shared stage-attempt lifecycle."""

from copy import deepcopy
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest
from testing_agent.domain.ai_tasks import AUXILIARY_EXECUTION_TYPES
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.repositories.auxiliary_execution import lock_or_create_stage
from testing_agent.services.stage_storage.dispatch import dispatch_stage_attempt


async def dispatch_auxiliary_execution(
    session: AsyncSession,
    *,
    task: AiGenerateTask,
    actor_id: str,
    request_id: str,
    execution_id: str,
    connection_id: str,
    source: dict[str, Any],
    config: dict[str, Any],
    trigger_type: str = "manual",
    request_signature: str | None = None,
) -> tuple[AiGenerationAttempt, bool]:
    """Create one execution and queue attempt in the caller's authorized transaction.

    The caller locks the owning task, verifies its scope and the actor's personal
    connections, and commits. A replay returns the original attempt and identity.
    """
    if (
        task.task_type not in AUXILIARY_EXECUTION_TYPES
        or not actor_id
        or not request_id
        or not execution_id
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
    stage = await lock_or_create_stage(session, task.task_id)
    attempt, replay = await dispatch_stage_attempt(
        session,
        task=task,
        stage_id=stage.id,
        request_id=request_id,
        actor_id=actor_id,
        input_snapshot={
            "source": frozen_source,
            "config": deepcopy(config),
            "llmConnectionId": connection_id,
            "triggerType": trigger_type,
            "requestSignature": request_signature,
        },
        new_execution_id=execution_id,
        review_required=False,
    )
    if replay:
        existing = attempt.input_snapshot_json or {}
        existing_source = existing.get("source") or {}
        if not isinstance(existing_source, dict):
            raise ErrBadRequest()
        existing_source = dict(existing_source)
        expected_source = dict(frozen_source)
        existing_source.pop("attemptId", None)
        existing_source.pop("runId", None)
        expected_source.pop("attemptId", None)
        expected_source.pop("runId", None)
        if (
            existing.get("requestSignature") != request_signature
            or existing.get("llmConnectionId") != connection_id
            or existing.get("triggerType", "manual") != trigger_type
            or (request_signature is None and existing_source != expected_source)
            or existing.get("config") != config
        ):
            raise ErrBadRequest()
        if request_signature is not None:
            from testing_agent.services.stage_storage.authorization import authorize_worker_actor

            await authorize_worker_actor(session, task, attempt)
    return attempt, replay
