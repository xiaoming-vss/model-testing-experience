"""Adapt an independent UI candidate to the existing formal import operation."""

from collections.abc import Awaitable, Callable
from typing import Any

from testing_agent.core.errors import ErrNotFound
from testing_agent.repositories.standalone_import import lock_target_and_count
from testing_agent.services.ai_task_access import CandidateImportContext
from testing_agent.services.standalone_import_flow import import_standalone_candidate
from testing_agent.services.standalone_run import StandaloneRun


async def import_standalone_ui(
    service: CandidateImportContext,
    run: StandaloneRun,
    *,
    suite_id: str,
    confirm_overwrite: bool,
    user_id: str,
    apply_import: Callable[..., Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    suite = await service.repository.get_ui_suite(suite_id)
    if suite is None:
        raise ErrNotFound()
    await service.ensure_requirement_access(user_id, suite.requirement_id, action="execute")
    await lock_target_and_count(
        service.repository.session,
        target_type="ui_suite",
        target_id=suite_id,
        project_id=run.project_id,
        changed_case_ids=(),
    )

    async def apply(source: StandaloneRun, content: str) -> dict[str, Any]:
        return await apply_import(
            service,
            run.run_id,
            suite_id,
            confirm_overwrite,
            user_id,
            artifact_content=content,
            approved_source=source,
        )

    return await import_standalone_candidate(
        service.repository, run, task_type="ui_case_generate", user_id=user_id, apply=apply
    )
