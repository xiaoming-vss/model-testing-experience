"""authority resolution for a stage-owned Worker task."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrForbidden
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.user import User
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.personal_authorization import require_personal_connection
from testing_agent.services.project_access import require_project_id


@dataclass(frozen=True)
class DirectWorkerAuthority:
    stage_id: str
    attempt_id: str
    actor_id: str
    task: AiGenerateTask
    input_snapshot: dict[str, Any]
    revision_instruction: str | None


@dataclass(frozen=True)
class DirectRevocationIdentity:
    actor_id: str
    project_id: str
    connection_ids: frozenset[str]


async def direct_revocation_identity(
    session: AsyncSession, queue_task: WorkerTask
) -> DirectRevocationIdentity | None:
    """Read immutable dispatch ownership without requiring the already revoked authority."""
    row = (
        await session.execute(
            select(AiGenerationAttempt, AiGenerateTask)
            .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
            .join(AiGenerateTask, AiGenerateTask.task_id == AiGenerationStage.task_id)
            .where(
                AiGenerationAttempt.id == queue_task.run_id,
                AiGenerationAttempt.worker_task_id == queue_task.task_id,
                AiGenerateTask.task_type == queue_task.task_type,
            )
        )
    ).one_or_none()
    if row is None or not row[0].requested_by:
        return None
    attempt, task = row
    snapshot = attempt.input_snapshot_json or {}
    source = snapshot.get("source") or {}
    bindings = source.get("bindings") or [] if isinstance(source, dict) else []
    ids = {str(snapshot.get("llmConnectionId") or "")}
    if isinstance(bindings, list):
        ids.update(
            str(binding.get("connectionId") or "")
            for binding in bindings
            if isinstance(binding, dict)
        )
    ids.discard("")
    return DirectRevocationIdentity(attempt.requested_by, task.project_id, frozenset(ids))


async def authorize_stage_worker(
    session: AsyncSession, queue_task: WorkerTask, *, pending: bool = False
) -> DirectWorkerAuthority:
    """Resolve current stage attempt, then recheck the dispatcher's permissions."""
    if queue_task.domain != "ai" or queue_task.status not in (
        {"pending", "claimed", "running"} if pending else {"claimed", "running"}
    ):
        raise ErrForbidden()
    row = (
        await session.execute(
            select(AiGenerationAttempt, AiGenerationStage, AiGenerateTask)
            .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
            .join(AiGenerateTask, AiGenerateTask.task_id == AiGenerationStage.task_id)
            .where(
                AiGenerationAttempt.id == queue_task.run_id,
                AiGenerationAttempt.worker_task_id == queue_task.task_id,
                AiGenerationStage.active_attempt_id == AiGenerationAttempt.id,
                AiGenerateTask.task_type == queue_task.task_type,
                AiGenerationAttempt.status.in_({"pending", "claimed", "running"}),
            )
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if row is None:
        raise ErrForbidden()
    attempt, stage, task = row
    actor = await authorize_worker_actor(session, task, attempt)
    snapshot = attempt.input_snapshot_json or {}
    return DirectWorkerAuthority(
        stage.id, attempt.id, actor, task, snapshot, attempt.revision_instruction
    )


async def authorize_worker_actor(
    session: AsyncSession, task: AiGenerateTask, attempt: AiGenerationAttempt
) -> str:
    """Recheck the original dispatcher's scope and personal credentials."""
    actor = attempt.requested_by or ""
    snapshot = attempt.input_snapshot_json or {}
    source = snapshot.get("source") or {}
    if not actor or not isinstance(source, dict):
        raise ErrForbidden()
    if not await session.scalar(select(User.user_id).where(User.user_id == actor)):
        raise ErrForbidden()
    await require_project_id(
        session,
        actor,
        task.project_id,
        action="execute" if task.task_type == "test_order_case_visualization" else "read",
    )
    if task.task_type == "test_order_case_visualization":
        from testing_agent.models.case_visualization import TestOrderEntryVisualization
        from testing_agent.models.test_order_entry import TestOrderEntry

        entry = await session.scalar(
            select(TestOrderEntry)
            .join(
                TestOrderEntryVisualization,
                TestOrderEntryVisualization.entry_id == TestOrderEntry.entry_id,
            )
            .where(
                TestOrderEntryVisualization.task_id == task.task_id,
                TestOrderEntry.entry_id == source.get("entryId"),
                TestOrderEntry.order_id == task.order_id,
            )
        )
        if entry is None:
            raise ErrForbidden()
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.services.ai_task_scope import GenerationAccess

    await GenerationAccess(AiGenerateTaskRepository(session)).validate_task_scope(task)
    connection_id = snapshot.get("llmConnectionId")
    if not isinstance(connection_id, str) or not connection_id:
        raise ErrForbidden()
    await require_personal_connection(session, actor, "llm", connection_id, task.project_id)
    bindings = source.get("bindings") or []
    if not isinstance(bindings, list):
        raise ErrForbidden()
    for binding in bindings:
        if not isinstance(binding, dict):
            raise ErrForbidden()
        if task.task_type == "repository_profile" and binding.get("profileError"):
            continue
        if not isinstance(binding.get("connectionId"), str):
            raise ErrForbidden()
        if task.task_type == "repository_profile" and not binding["connectionId"]:
            continue
        connection = await require_personal_connection(
            session, actor, "gitlab", binding["connectionId"], task.project_id
        )
        from testing_agent.services.service_instance import normalize_instance_url

        if binding.get("instanceUrl") != normalize_instance_url(connection.base_url):
            raise ErrForbidden()
    return actor
