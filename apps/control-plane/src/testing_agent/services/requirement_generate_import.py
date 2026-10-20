from __future__ import annotations

from testing_agent.core.enums import ReviewStatus, RunStatus
from testing_agent.core.errors import (
    ErrBadRequest,
    ErrNotFound,
)
from testing_agent.domain.ai_execution_intent import ExecutionIntent
from testing_agent.services.ai_task_access import CandidateImportContext
from testing_agent.services.ai_task_output import (
    requirement_analysis_import_content,
)
from testing_agent.services.requirement import dump_requirement


async def import_requirement_analysis_run(
    context: CandidateImportContext, run_id: str, user_id: str
) -> dict:
    run = await context.owned_run(user_id, run_id, "requirement_analysis", action="execute")
    if run.status != RunStatus.SUCCESS.value or run.review_status != ReviewStatus.APPROVED.value:
        raise ErrBadRequest()
    requirement = await context.repository.get_requirement(run.requirement_id)
    if requirement is None:
        raise ErrNotFound()
    await context.ensure_requirement_access(user_id, requirement.requirement_id, action="execute")
    requirement.document_content = requirement_analysis_import_content(run)
    await context.execution.save(
        context.repository.session, run, intent=ExecutionIntent(actor_id=user_id)
    )
    await context.repository.commit()
    await context.repository.refresh(requirement)
    return dump_requirement(requirement)
