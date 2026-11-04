"""Record formal-asset provenance for an approved independent candidate."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest
from testing_agent.core.sid import new_id
from testing_agent.domain.ai_execution_format import final_review_stage
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
from testing_agent.repositories.standalone_import import lock_target_and_count
from testing_agent.services.standalone_candidate import lock_standalone_candidate
from testing_agent.services.standalone_execution import workflow_stage_names


@dataclass(frozen=True)
class ImportChange:
    target_type: str
    target_id: str
    changed_case_ids: tuple[str, ...]


async def _record_standalone_import(
    session: AsyncSession,
    *,
    task: AiGenerateTask,
    execution_id: str,
    attempt_id: str,
    actor_id: str,
    changes: list[ImportChange],
) -> list[AiGenerateVersionImport]:
    """Record checked changes and effective pointers in the caller's transaction.

    The caller authorizes the task and all targets, locks parents before children,
    handles conflicts, and owns commit. No external work belongs in this transaction.
    """
    allowed = {
        "functional_case_generate": "function_suite",
        "api_case_generate": "api_collection",
        "ui_case_generate": "ui_suite",
    }
    if not actor_id or not changes or task.task_type not in allowed:
        raise ErrBadRequest()
    targets = [(change.target_type, change.target_id) for change in changes]
    if len(set(targets)) != len(targets) or any(
        kind != allowed[task.task_type] for kind, _ in targets
    ):
        raise ErrBadRequest()
    # Caller has locked the task. This locks execution, stage and candidate;
    # its current-stage check also prevents importing an obsolete revision.
    from testing_agent.models.ai_execution import AiExecution

    execution = await session.get(AiExecution, execution_id)
    if execution is None:
        raise ErrBadRequest()
    names = workflow_stage_names(task.task_type, execution.source_snapshot_json or {})
    final = final_review_stage(task.task_type, names)
    execution, _, attempt = await lock_standalone_candidate(
        session, task=task, execution_id=execution_id, stage_name=final
    )
    if (
        execution.workflow_status != "success"
        or attempt.id != attempt_id
        or attempt.review_status != "approved"
        or not attempt.reviewer_user_id
        or attempt.reviewed_at is None
    ):
        raise ErrBadRequest()
    now = datetime.now(UTC)
    records = []
    # Stable lock order avoids opposing target orders for multi-suite imports.
    for change in sorted(changes, key=lambda item: (item.target_type, item.target_id)):
        target, case_count = await lock_target_and_count(
            session,
            target_type=change.target_type,
            target_id=change.target_id,
            project_id=task.project_id,
            changed_case_ids=change.changed_case_ids,
        )
        record = AiGenerateVersionImport(
            import_id=f"vi-{new_id()}",
            task_id=task.task_id,
            version_id=None,
            attempt_id=attempt.id,
            leaf_stage=final,
            target_type=change.target_type,
            target_id=change.target_id,
            parent_versions_json=None,
            changed_case_ids_json=sorted(change.changed_case_ids),
            target_case_count=case_count,
            mixed_source=case_count > len(change.changed_case_ids),
            reviewer_user_id=attempt.reviewer_user_id,
            reviewed_at=attempt.reviewed_at,
            review_comment=attempt.review_comment or "",
            imported_by=actor_id,
            imported_at=now,
        )
        session.add(record)
        target.effective_import_id = record.import_id
        records.append(record)
    await session.flush()
    return records


async def record_standalone_import(
    session: AsyncSession,
    *,
    task: AiGenerateTask,
    execution_id: str,
    attempt_id: str,
    actor_id: str,
    changes: list[ImportChange],
) -> list[AiGenerateVersionImport]:
    """Atomically record all target changes; the caller commits the outer transaction."""
    async with session.begin_nested():
        return await _record_standalone_import(
            session,
            task=task,
            execution_id=execution_id,
            attempt_id=attempt_id,
            actor_id=actor_id,
            changes=changes,
        )
