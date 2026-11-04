"""Import an independent functional candidate into an explicitly chosen requirement."""

from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any

from testing_agent.core.errors import ErrBadRequest, ErrNotFound, dynamic_error
from testing_agent.repositories.standalone_import import requirement_project
from testing_agent.services.ai_task_access import CandidateImportContext
from testing_agent.services.standalone_import_flow import import_standalone_candidate
from testing_agent.services.standalone_run import StandaloneRun


async def import_standalone_function(
    service: CandidateImportContext,
    run: StandaloneRun,
    *,
    target_requirement_id: str | None,
    confirm_overwrite: bool,
    user_id: str,
    apply_import: Callable[..., Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    if not target_requirement_id:
        raise dynamic_error(ErrBadRequest, "请选择导入目标需求")
    await service.ensure_requirement_access(user_id, target_requirement_id, action="write")
    project_id = await requirement_project(service.repository.session, target_requirement_id)
    if project_id != run.project_id:
        raise ErrNotFound()

    async def apply(source: StandaloneRun, content: str) -> dict[str, Any]:
        target_source = deepcopy(source)
        target_source.requirement_id = target_requirement_id
        return await apply_import(
            service,
            run.run_id,
            confirm_overwrite,
            user_id,
            artifact_content=content,
            approved_source=target_source,
        )

    return await import_standalone_candidate(
        service.repository, run, task_type="functional_case_generate", user_id=user_id, apply=apply
    )
