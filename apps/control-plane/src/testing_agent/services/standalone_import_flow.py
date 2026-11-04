"""Shared transaction for importing reviewed independent candidates."""

from collections.abc import Awaitable, Callable
from typing import Any

from testing_agent.core.errors import ErrBadRequest
from testing_agent.domain.ai_execution_format import final_review_stage
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.ai_task_output import dump_run
from testing_agent.services.standalone_candidate import lock_standalone_candidate
from testing_agent.services.standalone_execution import workflow_stage_names
from testing_agent.services.standalone_execution_view import project_standalone_execution
from testing_agent.services.standalone_import import ImportChange, record_standalone_import
from testing_agent.services.standalone_run import StandaloneRun


async def import_standalone_candidate(
    repository: AiGenerateTaskRepository,
    run: StandaloneRun,
    *,
    task_type: str,
    user_id: str,
    apply: Callable[[StandaloneRun, str], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """Apply checked formal changes and source records in one transaction."""
    task = await repository.get_task_for_update(run.task_id)
    if task is None or task.task_type != task_type or task.requirement_id:
        raise ErrBadRequest()
    stage = final_review_stage(
        task.task_type, workflow_stage_names(task.task_type, run.snapshot_json)
    )
    execution, _, attempt = await lock_standalone_candidate(
        repository.session, task=task, execution_id=run.run_id, stage_name=stage
    )
    if (
        execution.workflow_status != "success"
        or attempt.review_status != "approved"
        or not attempt.output_content
    ):
        raise ErrBadRequest()
    current = await project_standalone_execution(repository.session, run.run_id)
    if current.import_status == "imported":
        raise ErrBadRequest()
    async with repository.session.begin_nested():
        result = await apply(current, attempt.output_content)
        if result.get("requiresConfirmation"):
            result["run"] = dump_run(
                await project_standalone_execution(repository.session, run.run_id)
            )
            return result
        changes = [
            ImportChange(
                target_type=str(change.get("targetType") or ""),
                target_id=str(change.get("targetId") or ""),
                changed_case_ids=tuple(
                    str(value) for value in (change.get("changedCaseIds") or [])
                ),
            )
            for change in result.get("importChanges") or []
        ]
        await record_standalone_import(
            repository.session,
            task=task,
            execution_id=run.run_id,
            attempt_id=attempt.id,
            actor_id=user_id,
            changes=changes,
        )
    await repository.commit()
    result["run"] = dump_run(await project_standalone_execution(repository.session, run.run_id))
    return result
