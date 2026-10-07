"""Shared write fence for compatibility paths; call under the project write lock."""

from sqlalchemy import or_, select

from testing_agent.core.errors import AppError
from testing_agent.models.integration_job import IntegrationJob


async def require_no_active_job(session, bug_id):
    from testing_agent.services.integration_runtime import isolated_scope

    if await isolated_scope(session, bug_id):
        raise AppError(409, "该 Bug 的恢复结果尚未核对，继续保持隔离", 409)
    active = await session.scalar(
        select(IntegrationJob.job_id)
        .where(
            IntegrationJob.bug_id == bug_id,
            or_(
                IntegrationJob.active_scope.is_not(None), IntegrationJob.recovery_required.is_(True)
            ),
        )
        .with_for_update()
    )
    if active is not None:
        raise AppError(409, "该 Bug 已有异步集成任务，请等待任务结果", 409)
