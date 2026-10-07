"""Join trusted read-only recovery to the original execution ledger in its local transaction."""

from typing import Any

from sqlalchemy import select

from testing_agent.core.errors import AppError, ErrForbidden, ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.domain.integration_execution import StepStatus, digest, same_result
from testing_agent.models.bug import Bug
from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.models.integration_job import IntegrationJob, IntegrationJobStep
from testing_agent.models.project import Project
from testing_agent.models.project_member import ProjectMember
from testing_agent.models.user import User
from testing_agent.schemas.integration_job import IntegrationRemoteResult
from testing_agent.services.integration_guards import require_no_active_job
from testing_agent.services.project_access import allowed_actions
from testing_agent.services.service_instance import instance_key


async def lock_recovery(session, bug_id: str, actor: str | None = None) -> None:
    project_id = await session.scalar(select(Bug.project_id).where(Bug.bug_id == bug_id))
    if project_id is None:
        raise ErrNotFound()
    project = await session.scalar(
        select(Project)
        .where(Project.project_id == project_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if project is None:
        raise ErrNotFound()
    if actor is not None:
        # A read-only network call may outlive membership changes. Read current locked facts.
        user = await session.scalar(
            select(User)
            .where(User.user_id == actor)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        member = await session.scalar(
            select(ProjectMember)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == actor,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        role = "owner" if project.user_id == actor else member.role if member is not None else ""
        if user is None or "write" not in allowed_actions(role):
            raise ErrForbidden()
    await require_no_active_job(session, bug_id)


async def record_verified_recovery(
    session,
    bug_id: str,
    operation_id: str,
    kind: str,
    result: IntegrationRemoteResult,
    *,
    actor: str | None = None,
):
    """Caller has locked the project and applied a verified domain CAS, but has not committed."""
    from testing_agent.services.integration_job import summary
    from testing_agent.services.integration_lifecycle import associated_unknown, lifecycle

    candidates = (
        await session.execute(
            select(IntegrationJob.job_id, IntegrationJobStep.step_key)
            .join(IntegrationJobStep, IntegrationJobStep.job_id == IntegrationJob.job_id)
            .where(
                IntegrationJob.bug_id == bug_id,
                IntegrationJobStep.operation_id == operation_id,
                IntegrationJobStep.kind == kind,
                # Readonly no-ops are already confirmed; they are never a write to recover.
                IntegrationJobStep.status != StepStatus.NOOP,
            )
            .limit(2)
        )
    ).all()
    if not candidates:
        return  # A pre-split operation has no execution ledger.
    if len(candidates) != 1:
        raise AppError(409, "原操作对应多个执行步骤，不能自动恢复", 409)
    jobs = lifecycle(session)
    job = await jobs.locked(candidates[0].job_id)
    step = await jobs.step(job.job_id, candidates[0].step_key)
    facts = result.model_dump(mode="json", by_alias=True, exclude_none=True)
    if step.status == StepStatus.SUCCEEDED and same_result(kind, step.result_json, facts):
        return
    if step.status != StepStatus.UNKNOWN or not await associated_unknown(session, job, step):
        raise AppError(409, "原执行步骤已变化或仍在写入，不能按未知结果恢复", 409)
    row = await session.scalar(
        select(BugZentaoPush)
        .where(BugZentaoPush.bug_id == bug_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None or instance_key(row.instance_url) != job.target_key:
        raise AppError(409, "原恢复目标已变化", 409)
    if kind != "create_bug" and (
        row.operation_id != job.mapping_json.get("pushOperationId")
        or row.remote_bug_id != job.mapping_json.get("remoteBugId")
    ):
        raise AppError(409, "原恢复关联已变化", 409)
    if kind == "create_bug":
        if row.status != "succeeded" or row.remote_bug_id != result.remote_bug_id:
            raise AppError(409, "已核对 Bug 编号与原操作不一致", 409)
        job.mapping_json = {
            **job.mapping_json,
            "remoteBugId": row.remote_bug_id,
            "productId": row.payload_json.get("productID"),
        }
    elif kind == "upload_attachment":
        from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment

        file_id = step.step_key.split(":", 1)[1]
        record = await session.scalar(
            select(BugZentaoAttachment)
            .where(
                BugZentaoAttachment.bug_id == bug_id,
                BugZentaoAttachment.file_id == file_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        frozen: dict[str, Any] = next(
            (file for file in job.snapshot_json["source"]["files"] if file["fileId"] == file_id), {}
        )
        if (
            record is None
            or record.status != "succeeded"
            or record.operation_id != step.operation_id
            or record.remote_file_id != result.remote_file_id
            or record.sha256 != frozen.get("sha256")
        ):
            raise AppError(409, "已核对附件与原操作不一致", 409)
        job.mapping_json = {
            **job.mapping_json,
            "files": {
                **job.mapping_json.get("files", {}),
                file_id: {"remoteFileId": record.remote_file_id, "sha256": record.sha256},
            },
        }
    elif kind == "update_fields":
        from testing_agent.services.bug_zentao_fields import KEY, equal

        if (
            row.payload_json.get(KEY, {}).get("status") != "succeeded"
            or set(facts) != {"openedBuild", "assignedTo"}
            or not equal(facts, job.snapshot_json["desired"])
        ):
            raise AppError(409, "字段核对结果与原指定值不一致", 409)
    else:
        from testing_agent.services.bug_zentao_description import source_hash

        if (
            row.description_status != "succeeded"
            or result.description_hash != source_hash(row.description_sync_json["desiredSteps"])
            or result.description_hash != source_hash(step.input_json["desiredSteps"])
        ):
            raise AppError(409, "正文核对结果与原内容不一致", 409)
    step.status, step.result_json = StepStatus.SUCCEEDED, facts
    await jobs.finish(job)
    response = {
        **summary(job),
        "stepKey": step.step_key,
        "status": step.status,
        "operationId": step.operation_id,
        "mapping": job.mapping_json,
    }
    step.receipts_json = [
        *step.receipts_json,
        {
            "eventId": "recovery:" + new_id(),
            "digest": digest(facts),
            "response": response,
            "source": "readonly_recovery",
            "actorUserId": actor,
        },
    ]
    await session.flush()
