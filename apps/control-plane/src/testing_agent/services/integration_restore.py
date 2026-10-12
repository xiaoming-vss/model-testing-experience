"""Maintenance-only restore decisions. Remote reads precede local CAS transactions."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select

from testing_agent.core.errors import ErrForbidden, ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.domain.integration_execution import digest, require_safe_snapshot, utc
from testing_agent.models.bug import Bug
from testing_agent.models.bug_activity import BugActivity
from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment
from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.models.integration_job import (
    IntegrationJob,
    IntegrationJobStep,
    IntegrationRestoreReview,
    IntegrationRuntime,
)
from testing_agent.models.project import Project
from testing_agent.models.stored_file import StoredFile
from testing_agent.models.user import User
from testing_agent.services.integration_authorization import IntegrationSubject
from testing_agent.services.integration_restore_read import read_restore_proof, require
from testing_agent.services.integration_runtime import key_digest
from testing_agent.services.integration_transaction import local_transaction
from testing_agent.services.service_instance import instance_key


def values(row):
    if row is None:
        return None
    return {
        column.key: utc(value).isoformat() if isinstance(value, datetime) else value
        for column in row.__table__.columns
        if column.key not in {"created_at", "updated_at"}
        for value in [getattr(row, column.key)]
    }


class IntegrationRestoreService:
    def __init__(
        self, session, pushes, authorization, settings, *, clock=lambda: datetime.now(UTC)
    ):
        self.session, self.pushes, self.authorization = session, pushes, authorization
        self.settings, self.clock = settings, clock

    async def fence(self, restore_id, *, released=False):
        runtime = await self.session.scalar(
            select(IntegrationRuntime)
            .where(IntegrationRuntime.id == 1)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        execution = self.settings.integration_execution
        require(runtime is not None and runtime.restore_id == restore_id, "恢复环境编号已变化")
        require(
            execution.runtime_generation == runtime.runtime_generation
            and key_digest(self.settings.integration_worker_key) == runtime.worker_key_digest,
            "恢复配置的运行代次或专属令牌不匹配",
        )
        require(
            not execution.enabled
            and not execution.accept_submissions
            and not execution.claim_enabled,
            "核对和放行要求执行、提交及领取开关关闭",
        )
        require(runtime.blocked or released, "恢复环境已放行，请使用正常核对入口")
        return runtime

    async def owner(self, bug_id, actor):
        project_id = await self.session.scalar(select(Bug.project_id).where(Bug.bug_id == bug_id))
        if project_id is None:
            raise ErrNotFound()
        project = await self.session.scalar(
            select(Project)
            .where(Project.project_id == project_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        user = await self.session.scalar(
            select(User.user_id).where(User.user_id == actor).with_for_update()
        )
        if project is None or project.user_id != actor or user is None:
            raise ErrForbidden()
        return await self.session.scalar(
            select(Bug)
            .where(Bug.bug_id == bug_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def review(self, restore_id, scope_type, scope_id):
        return await self.session.scalar(
            select(IntegrationRestoreReview)
            .where(
                IntegrationRestoreReview.restore_id == restore_id,
                IntegrationRestoreReview.scope_type == scope_type,
                IntegrationRestoreReview.scope_id == scope_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def packet(self, bug_id, restore_id):
        bug = await self.session.scalar(
            select(Bug)
            .where(Bug.bug_id == bug_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if bug is None:
            raise ErrNotFound()
        row = await self.pushes.row(bug_id)
        if row:
            await self.session.refresh(row, with_for_update=True)
        attachments = (
            await self.session.scalars(
                select(BugZentaoAttachment)
                .where(BugZentaoAttachment.bug_id == bug_id)
                .order_by(BugZentaoAttachment.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
        files = (
            await self.session.scalars(
                select(StoredFile)
                .where(
                    StoredFile.resource_id == bug_id,
                    StoredFile.resource_type == "bug",
                    StoredFile.status == "attached",
                    StoredFile.purpose == "attachment",
                )
                .order_by(StoredFile.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
        jobs = (
            await self.session.scalars(
                select(IntegrationJob)
                .where(IntegrationJob.bug_id == bug_id, IntegrationJob.recovery_required.is_(True))
                .order_by(IntegrationJob.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
        selected = jobs
        steps = (
            (
                await self.session.scalars(
                    select(IntegrationJobStep)
                    .where(IntegrationJobStep.job_id.in_([j.job_id for j in selected]))
                    .order_by(IntegrationJobStep.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
            if selected
            else []
        )
        packet = {
            "bug": values(bug),
            "push": values(row),
            "attachments": [values(v) for v in attachments],
            "files": [values(v) for v in files],
            "jobs": [values(v) for v in selected],
            "steps": [values(v) for v in steps],
        }
        return packet, (bug, row, attachments, selected, steps)

    async def context(self, restore_id, bug_id, actor):
        await self.fence(restore_id, released=True)
        bug = await self.owner(bug_id, actor)
        active = await self.session.scalar(
            select(IntegrationJob.job_id)
            .where(
                IntegrationJob.bug_id == bug_id,
                IntegrationJob.recovery_required.is_(False),
                IntegrationJob.status.in_(["queued", "claimed", "running", "unknown"]),
            )
            .limit(1)
            .with_for_update()
        )
        require(active is None, "当前任务尚未排空或结果未知，请使用正常核对入口")
        service, connection, target = await self.pushes.local_context(bug, actor, lock=True)
        subject = IntegrationSubject(
            bug.project_id, bug_id, actor, service.service_id, connection.connection_id
        )
        access = await self.authorization.access(subject)
        packet, entities = await self.packet(bug_id, restore_id)
        if packet["push"]:
            require(
                instance_key(packet["push"]["instance_url"]) == instance_key(target["instanceUrl"])
                and all(
                    packet["push"]["target_json"].get(k) == target[k]
                    for k in ("project", "execution", "story")
                ),
                "当前关联目标已变化",
            )
        fingerprint = digest(
            {"packet": packet, "target": target, "accessRevision": access.access_revision}
        )
        return {
            "packet": packet,
            "entities": entities,
            "target": target,
            "subject": subject,
            "access": access,
            "fingerprint": fingerprint,
            "target_key": instance_key(target["instanceUrl"]),
        }

    async def audit(self, request):
        context = await self.context(request.restore_id, request.bug_id, request.actor_user_id)
        await self.session.commit()  # Never hold database locks while downloading remote files.
        facts = await read_restore_proof(self.pushes, context, request)
        require_safe_snapshot(facts)
        return await self.apply(request, context["fingerprint"], facts)

    async def save_review(
        self, restore_id, scope_type, scope_id, project_id, actor, decision, state
    ):
        row = await self.review(restore_id, scope_type, scope_id)
        if row is None:
            row = IntegrationRestoreReview(
                review_id=new_id(),
                restore_id=restore_id,
                scope_type=scope_type,
                scope_id=scope_id,
                project_id=project_id,
                actor_user_id=actor,
                decision=decision,
                state_digest=state,
                reviewed_at=self.clock(),
            )
            self.session.add(row)
        else:
            row.actor_user_id, row.decision, row.state_digest = actor, decision, state
            row.reviewed_at = self.clock()
        await self.session.flush()
        return row

    @local_transaction
    async def apply(self, request, fingerprint, facts):
        context = await self.context(request.restore_id, request.bug_id, request.actor_user_id)
        require(
            context["fingerprint"] == fingerprint, "核对期间本地状态或本人授权已变化，请重新核对"
        )
        bug, row, attachments, jobs, steps = context["entities"]
        if row is None:
            row = BugZentaoPush(
                bug_id=bug.bug_id,
                operation_id=new_id(),
                actor_user_id=request.actor_user_id,
                service_id=context["target"]["mcpServiceId"],
                instance_url=context["target"]["instanceUrl"],
                instance_key=instance_key(context["target"]["instanceUrl"]),
                status="succeeded",
                remote_bug_id=request.remote_bug_id,
                target_json=context["target"],
                payload_json=next((j.snapshot_json.get("createPayload", {}) for j in jobs), {}),
            )
            self.session.add(row)
        original_operations = {s.id: s.operation_id for s in steps}
        for step in steps:
            if (
                step.kind == "create_bug"
                and step.operation_id
                and step.status in {"unknown", "write_intent"}
            ):
                require(
                    row.operation_id == step.operation_id,
                    "历史未知创建与当前关联不同，请保持该操作隔离",
                )
        row.status, row.remote_bug_id, row.error_message = "succeeded", request.remote_bug_id, ""
        row.service_id, row.target_json = context["target"]["mcpServiceId"], context["target"]
        row.payload_json = {**row.payload_json, "productID": facts["productId"], **facts["fields"]}
        field_state = row.payload_json.get("_fieldUpdate", {})
        if field_state.get("status") in {"preparing", "updating", "unknown"}:
            row.payload_json = {
                **row.payload_json,
                "_fieldUpdate": {**field_state, "status": "succeeded", "error": ""},
            }
        row.description_status = "succeeded"
        row.description_operation_id = row.description_operation_id or new_id()
        row.description_sync_json = {
            **(row.description_sync_json or {}),
            **facts["description"],
            "expectedSteps": facts["description"]["desiredSteps"],
        }
        row.description_updated_at = self.clock()
        records = {a.file_id: a for a in attachments}
        for identifier, proof in facts["files"].items():
            record = records.get(identifier)
            if record is None:
                record = BugZentaoAttachment(
                    bug_id=bug.bug_id,
                    file_id=identifier,
                    operation_id=new_id(),
                    actor_user_id=request.actor_user_id,
                    sha256=proof["sha256"],
                    remote_bug_id=request.remote_bug_id,
                    instance_url=row.instance_url,
                    status="succeeded",
                )
                self.session.add(record)
                records[identifier] = record
            require(
                record.sha256 == proof["sha256"] and record.remote_bug_id == request.remote_bug_id,
                "原文件内容或关联已变化",
            )
            record.remote_file_id, record.status, record.error_message = (
                proof["remoteFileId"],
                "succeeded",
                "",
            )
        for job in jobs:
            states = {}
            for step in (s for s in steps if s.job_id == job.job_id):
                operation = None
                if step.kind == "create_bug":
                    operation, result = row.operation_id, {"remoteBugId": request.remote_bug_id}
                elif step.kind == "upload_attachment":
                    record = records.get(step.step_key.split(":", 1)[1])
                    if record:
                        operation, result = (
                            record.operation_id,
                            {"remoteFileId": record.remote_file_id},
                        )
                elif step.kind == "update_description":
                    from testing_agent.services.bug_zentao_description import source_hash

                    operation, result = (
                        row.description_operation_id,
                        {"descriptionHash": source_hash(facts["description"]["desiredSteps"])},
                    )
                else:
                    operation, result = field_state.get("operationId") or new_id(), facts["fields"]
                if operation is None:
                    require(
                        step.status not in {"write_intent", "unknown"},
                        "有未核对的文件步骤，继续保持隔离",
                    )
                    step.status = "blocked"
                elif step.status not in {"succeeded", "noop", "failed", "canceled", "blocked"}:
                    if step.operation_id:
                        require(
                            step.operation_id == operation, "原写入操作与当前映射不同，请保持隔离"
                        )
                        step.status = "succeeded"
                    else:
                        # A readonly review has its own identity, not a remote write's identity.
                        step.operation_id, step.status = new_id(), "noop"
                    step.result_json = result
                    step.receipts_json = [
                        *step.receipts_json,
                        {
                            "eventId": "restore:" + new_id(),
                            "digest": digest(result),
                            "source": "restore_readonly_verification",
                            "actorUserId": request.actor_user_id,
                            "originalOperationId": original_operations[step.id],
                            "response": {"status": step.status, "operationId": step.operation_id},
                        },
                    ]
                states[step.step_key] = step.status
            job.recovery_required, job.status = False, "canceled"
            job.active_scope, job.active_target, job.lease_expires_at = None, None, None
            job.canceled_at, job.finished_at = self.clock(), self.clock()
            job.result_json = {
                **job.result_json,
                "steps": states,
                "reason": "restore_readonly_verified",
            }
            job.mapping_json = {
                **job.mapping_json,
                "remoteBugId": request.remote_bug_id,
                "pushOperationId": row.operation_id,
                "files": facts["files"],
            }
            previous = await self.review(request.restore_id, "job", job.job_id)
            if previous is not None:
                previous.decision = "verified"
                previous.state_digest = digest(values(job))
                previous.actor_user_id, previous.reviewed_at = request.actor_user_id, self.clock()
        await self.session.flush()
        current = await self.context(request.restore_id, request.bug_id, request.actor_user_id)
        review = await self.save_review(
            request.restore_id,
            "bug",
            bug.bug_id,
            bug.project_id,
            request.actor_user_id,
            "verified",
            current["fingerprint"],
        )
        if jobs:
            self.session.add(
                BugActivity(
                    activity_id=new_id(),
                    bug_id=bug.bug_id,
                    actor_user_id=request.actor_user_id,
                    kind="sync",
                    action="zentao_restore_review",
                    content="恢复核对完成，旧任务保留历史，后续操作需手动提交",
                    detail_json={"restoreId": request.restore_id, "reviewId": review.review_id},
                )
            )
        await self.session.commit()
        return {
            "reviewId": review.review_id,
            "decision": review.decision,
            "reviewedJobs": len(jobs),
        }

    @local_transaction
    async def isolate(self, restore_id, *, bug_id=None, job_id=None):
        await self.fence(restore_id, released=True)
        require(bool(bug_id) != bool(job_id), "隔离确认只能选择一个 Bug 或任务")
        if bug_id:
            packet, entities = await self.packet(bug_id, restore_id)
            project_id, state = entities[0].project_id, digest(packet)
            scope_type, scope_id = "bug", bug_id
        else:
            job = await self.session.scalar(
                select(IntegrationJob)
                .where(IntegrationJob.job_id == job_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            require(job is not None and job.recovery_required, "任务不在恢复隔离清单")
            project_id, state = job.project_id, digest(values(job))
            scope_type, scope_id = "job", job_id
        row = await self.save_review(
            restore_id,
            scope_type,
            scope_id,
            project_id,
            None,
            "isolated",
            state,
        )
        await self.session.commit()
        return {"reviewId": row.review_id, "decision": "isolated", "writesRemainBlocked": True}

    @local_transaction
    async def release(self, restore_id):
        runtime = await self.fence(restore_id, released=True)
        if not runtime.blocked:
            return {"restoreId": restore_id, "blocked": False}
        bugs = set(
            (
                await self.session.scalars(
                    select(BugZentaoPush.bug_id).where(
                        or_(
                            BugZentaoPush.remote_bug_id.is_not(None),
                            BugZentaoPush.status.in_(
                                ["creating", "unknown", "preparing", "succeeded"]
                            ),
                        )
                    )
                )
            ).all()
        )
        bugs.update((await self.session.scalars(select(BugZentaoAttachment.bug_id))).all())
        jobs = (
            await self.session.scalars(
                select(IntegrationJob)
                .where(IntegrationJob.recovery_required.is_(True))
                .order_by(IntegrationJob.project_id, IntegrationJob.id)
            )
        ).all()
        isolated = 0
        for job in jobs:
            decision = await self.review(restore_id, "job", job.job_id)
            if decision and decision.decision == "isolated":
                require(decision.state_digest == digest(values(job)), "隔离任务在确认后已变化")
                isolated += 1
            else:
                bugs.add(job.bug_id)
        for bug_id in sorted(bugs):
            decision = await self.review(restore_id, "bug", bug_id)
            require(decision is not None, "仍有未核对的映射或任务，恢复环境继续保持隔离")
            if decision.decision == "isolated":
                packet, _ = await self.packet(bug_id, restore_id)
                require(decision.state_digest == digest(packet), "隔离范围在确认后已变化")
                isolated += 1
            else:
                require(
                    utc(decision.reviewed_at)
                    + timedelta(
                        seconds=self.settings.integration_execution.restore_review_max_age_seconds
                    )
                    >= self.clock(),
                    "恢复核对已过期，请重新只读核对",
                )
                current = await self.context(restore_id, bug_id, decision.actor_user_id)
                require(
                    current["fingerprint"] == decision.state_digest,
                    "当前映射或授权已变化，请重新核对",
                )
        runtime.blocked = False
        await self.session.commit()
        return {
            "restoreId": restore_id,
            "blocked": False,
            "isolatedScopes": isolated,
            "oldTasksReplayed": False,
            "executionEnabled": False,
        }
