"""Resource mutation fences and revocation, without credentials or remote clients."""

from sqlalchemy import select

from testing_agent.core.errors import AppError, ErrForbidden
from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment
from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.models.integration_job import (
    IntegrationJob,
    IntegrationJobStep,
    IntegrationRestoreReview,
    IntegrationRuntime,
)
from testing_agent.models.project import Project
from testing_agent.repositories.integration_job import IntegrationJobRepository
from testing_agent.services.integration_bug_state import IntegrationBugState, reject_recovery
from testing_agent.services.integration_job import IntegrationJobService


async def unavailable(*args):
    raise ErrForbidden()


def lifecycle(session):
    async def lock_project(project_id):
        await session.scalar(
            select(Project)
            .where(Project.project_id == project_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    return IntegrationJobService(
        IntegrationJobRepository(session),
        authorize=unavailable,
        validate_prepare=unavailable,
        apply_result=unavailable,
        runtime_generation="lifecycle-only",
        lock_resource=lock_project,
        on_state=IntegrationBugState(session, record_recovery=reject_recovery).sync,
    )


async def revoke_integrations(
    session, *, actor="", project_id="", connection_id="", service_id="", bug_id=""
):
    filters = {
        key: value
        for key, value in {
            "actor_user_id": actor,
            "project_id": project_id,
            "connection_id": connection_id,
            "service_id": service_id,
            "bug_id": bug_id,
        }.items()
        if value
    }
    if filters:
        return await lifecycle(session).revoke(**filters)
    raise ValueError("Integration revocation requires a resource scope")


async def associated_unknown(session, job, step):
    row = await session.scalar(
        select(BugZentaoPush)
        .where(BugZentaoPush.bug_id == job.bug_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        return False
    if step.kind == "create_bug":
        return row.operation_id == step.operation_id
    if step.kind == "update_description":
        return row.description_operation_id == step.operation_id
    if step.kind == "update_fields":
        return row.payload_json.get("_fieldUpdate", {}).get("operationId") == step.operation_id
    attachment = await session.scalar(
        select(BugZentaoAttachment)
        .where(
            BugZentaoAttachment.bug_id == job.bug_id,
            BugZentaoAttachment.operation_id == step.operation_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return attachment is not None and attachment.remote_bug_id == row.remote_bug_id


async def guard_integrations(
    session, *, project_id, service_id="", bug_id="", include_unknown=True
):
    """Caller holds the project lock; archive/reset may explicitly allow old unknown facts."""
    await session.scalar(
        select(Project)
        .where(Project.project_id == project_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    query = (
        select(IntegrationJob, IntegrationJobStep)
        .join(
            IntegrationJobStep,
            IntegrationJobStep.job_id == IntegrationJob.job_id,
        )
        .where(
            IntegrationJob.project_id == project_id,
            IntegrationJobStep.status.in_(["write_intent", "unknown"]),
        )
    )
    if service_id:
        query = query.where(IntegrationJob.service_id == service_id)
    if bug_id:
        query = query.where(IntegrationJob.bug_id == bug_id)
    quarantined = select(IntegrationJob.job_id).where(
        IntegrationJob.project_id == project_id,
        IntegrationJob.recovery_required.is_(True),
    )
    if service_id:
        quarantined = quarantined.where(IntegrationJob.service_id == service_id)
    if bug_id:
        quarantined = quarantined.where(IntegrationJob.bug_id == bug_id)
    if await session.scalar(quarantined.limit(1).with_for_update()) is not None:
        raise AppError(409, "有恢复隔离任务，请完成外部核对后再修改关联或删除", 409)
    isolated = (
        select(IntegrationRestoreReview.review_id)
        .join(
            IntegrationRuntime, IntegrationRuntime.restore_id == IntegrationRestoreReview.restore_id
        )
        .where(
            IntegrationRuntime.id == 1,
            IntegrationRestoreReview.project_id == project_id,
            IntegrationRestoreReview.scope_type == "bug",
            IntegrationRestoreReview.decision == "isolated",
        )
    )
    if bug_id:
        isolated = isolated.where(IntegrationRestoreReview.scope_id == bug_id)
    if await session.scalar(isolated.limit(1).with_for_update()) is not None:
        raise AppError(409, "有恢复隔离范围，请完成核对后再修改关联或删除", 409)
    for job, step in (
        await session.execute(query.order_by(IntegrationJob.id).with_for_update())
    ).all():
        if step.status == "write_intent" or (
            include_unknown and await associated_unknown(session, job, step)
        ):
            raise AppError(409, "有集成写入正在执行或结果未核对，请完成核对后再修改关联或删除", 409)


async def change_target(session, *, project_id, service_id="", include_unknown=True):
    await guard_integrations(
        session, project_id=project_id, service_id=service_id, include_unknown=include_unknown
    )
    await revoke_integrations(session, project_id=project_id, service_id=service_id)
