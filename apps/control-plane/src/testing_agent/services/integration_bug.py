"""Bug integration coordinator: local commands, lease protocol and atomic domain receipts."""

import logging
from typing import Any

from sqlalchemy import select

from testing_agent.core.errors import AppError, ErrNotFound
from testing_agent.domain.integration_execution import StepStatus, digest
from testing_agent.models.bug_zentao_sync_baseline import BugZentaoSyncBaseline
from testing_agent.models.integration_job import IntegrationJob
from testing_agent.models.project import Project
from testing_agent.services.bug_zentao_attachment import BugZentaoAttachmentService
from testing_agent.services.bug_zentao_description import description_summary
from testing_agent.services.integration_bug_context import IntegrationBugContext, require
from testing_agent.services.integration_bug_steps import IntegrationBugSteps
from testing_agent.services.integration_job import IntegrationJobService, summary
from testing_agent.services.integration_observation import IntegrationObservation
from testing_agent.services.integration_runtime import (
    isolated_scope,
    require_runtime,
    restored_runtime,
)
from testing_agent.services.integration_transaction import local_transaction

logger = logging.getLogger(__name__)


class IntegrationBugService:
    def __init__(self, repository, pushes, authorization, settings):
        self.repository, self.pushes = repository, pushes
        self.session, self.authorization = repository.session, authorization
        self.settings = settings
        self.context = IntegrationBugContext(pushes)
        self.steps = IntegrationBugSteps(
            self.session, context=self.context, authorization=authorization
        )
        execution = settings.integration_execution
        self.jobs = IntegrationJobService(
            repository,
            authorize=self.authorize,
            validate_prepare=self.steps.validate,
            apply_result=self.steps.apply,
            on_prepare=self.steps.reserve,
            on_state=self.steps.sync,
            lock_resource=self.lock_project,
            runtime_generation=execution.runtime_generation or "disabled",
            lease_seconds=execution.lease_seconds,
        )
        self.observation = IntegrationObservation(
            self.session, settings, clock=lambda: self.jobs.clock()
        )

    async def lock_project(self, project_id):
        # A missing project is allowed only for recording already-issued write evidence.
        await self.session.scalar(
            select(Project)
            .where(Project.project_id == project_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def authorize(self, job):
        require(
            not await isolated_scope(self.session, job.bug_id),
            "该 Bug 的恢复结果尚未核对，继续保持隔离",
        )
        require(
            self.settings.integration_execution.uses_worker(job.project_id),
            "该项目已暂停集成执行，请等待核对或恢复",
        )
        try:
            await self.authorization.authorize(job)
        except AppError as error:
            logger.warning(
                "Integration authorization rejected job=%s service=%s status=%s",
                job.job_id,
                job.service_id,
                error.http_code,
            )
            raise

    async def admit(self, actor, bug_id, request, task_type):
        await require_runtime(self.session, self.settings)
        require(
            not await isolated_scope(self.session, bug_id),
            "该 Bug 的恢复结果尚未核对，继续保持隔离",
        )
        bug = await self.pushes.bugs.get_accessible_entity(actor, bug_id, action="write")
        await self.lock_project(bug.project_id)
        execution = self.settings.integration_execution
        require(
            execution.uses_worker(bug.project_id) and execution.accept_submissions,
            "该项目尚未启用或已暂停异步集成提交",
        )
        request_id = request.request_id
        existing = await self.repository.by_request(actor, request_id, lock=True)
        client_digest = digest(request.model_dump(mode="json", by_alias=True))
        if existing is not None:
            require(
                existing.bug_id == bug_id
                and existing.task_type == task_type
                and existing.snapshot_json.get("clientRequest") == client_digest,
                "相同请求编号对应不同操作",
            )
            return existing
        body = await (
            self.context.build_sync(actor, bug_id, request_id, request)
            if task_type == "zentao_bug_sync"
            else self.context.build_fields(actor, bug_id, request_id, request)
        )
        job = await self.jobs.submit(body)
        blocked = set(job.snapshot_json.get("blockedSteps", []))
        for step in await self.repository.steps(job.job_id, lock=True):
            if step.step_key in blocked:
                step.status = StepStatus.BLOCKED
                step.result_json = {"reason": "historical_unknown"}
        return job

    @local_transaction
    async def submit(self, actor, bug_id, request, task_type):
        job = await self.admit(actor, bug_id, request, task_type)
        await self.session.commit()
        return summary(job)

    async def get(self, actor, bug_id, job_id):
        await self.pushes.bugs.get_accessible_entity(actor, bug_id)
        job = await self.repository.get(job_id)
        if job is None or job.bug_id != bug_id:
            raise ErrNotFound()
        return await self.observed_summary(job)

    async def observed_summary(self, job):
        return {**summary(job), **await self.observation.explain(job)}

    async def guard_recovery(self, actor: str, bug_id: str) -> None:
        await self.pushes.bugs.get_accessible_entity(actor, bug_id, action="write")
        require(
            await self.repository.active(bug_id) is None,
            "该 Bug 已有异步任务，请等待结果后再执行核对或修改",
        )

    async def status(self, actor, bug_id):
        bug = await self.pushes.bugs.get_accessible_entity(actor, bug_id)
        active, latest = await self.repository.active(bug_id), await self.repository.latest(bug_id)
        runtime = await restored_runtime(self.session)
        quarantine = await self.session.scalar(
            select(IntegrationJob.job_id)
            .where(IntegrationJob.bug_id == bug_id, IntegrationJob.recovery_required.is_(True))
            .limit(1)
        ) is not None or await isolated_scope(self.session, bug_id)
        recovering = runtime is not None and runtime.blocked
        fields: dict[str, Any] = {
            "execution_mode": "worker",
            "active_job": await self.observed_summary(active) if active else None,
            "latest_job": await self.observed_summary(latest) if latest else None,
        }
        row = await self.pushes.row(bug_id)
        if row and row.status == "succeeded":
            fields.update(await BugZentaoAttachmentService(self.pushes).summary(bug, row))
            imported_local_digest = None
            if row.source == "import":
                # 导入方向的图片是否补齐由拉取管线写入的描述基线判定。
                baseline = await self.session.scalar(
                    select(BugZentaoSyncBaseline).where(
                        BugZentaoSyncBaseline.bug_id == bug_id,
                        BugZentaoSyncBaseline.field_group == "description",
                    )
                )
                imported_local_digest = (
                    (baseline.local_snapshot_json or {}).get("digest") if baseline else None
                )
            fields.update(
                description_summary(bug, row, imported_local_digest=imported_local_digest)
            )
        try:
            await self.pushes.bugs.get_accessible_entity(actor, bug_id, action="write")
            _, _, target = await self.context.local_target(bug, actor, row)
            fields.update(
                target=target,
                ready=active is None
                and self.settings.integration_execution.uses_worker(bug.project_id)
                and self.settings.integration_execution.accept_submissions,
            )
        except AppError as error:
            fields.update(ready=False, reason=error.message)
        if recovering:
            fields.update(ready=False, reason="恢复环境的外部集成尚未核对，已暂停所有远端写入")
        elif quarantine:
            fields.update(ready=False, reason="该 Bug 的恢复结果尚未核对，继续保持隔离")
        elif not self.settings.integration_execution.uses_worker(bug.project_id):
            fields.update(ready=False, reason="集成执行已暂停，请等待恢复或核对")
        return self.pushes.response(row, **fields)

    @local_transaction
    async def claim(self, body):
        await require_runtime(self.session, self.settings, worker=True)
        execution = self.settings.integration_execution
        response = await self.jobs.claim(
            body, enabled=execution.enabled and execution.claim_enabled
        )
        await self.observation.contact(body)
        await self.session.commit()
        return response

    @local_transaction
    async def input(self, job_id, identity):
        await require_runtime(self.session, self.settings, worker=True)
        response = await self.jobs.input(job_id, identity)
        await self.session.commit()
        return response

    @local_transaction
    async def access(self, job_id, identity):
        await require_runtime(self.session, self.settings, worker=True)
        job = await self.jobs.owned(job_id, identity)
        try:
            material = await self.authorization.access(job)
        except AppError as error:
            logger.warning(
                "Integration authorization rejected job=%s service=%s status=%s",
                job.job_id,
                job.service_id,
                error.http_code,
            )
            raise
        await self.session.commit()
        return {
            "endpoint": material.endpoint,
            "token": material.token.get_secret_value(),
            "accessRevision": material.access_revision,
        }

    @local_transaction
    async def heartbeat(self, job_id, body):
        await require_runtime(self.session, self.settings, worker=True)
        response = await self.jobs.heartbeat(job_id, body)
        await self.observation.heartbeat(body)
        await self.session.commit()
        return response

    @local_transaction
    async def prepare(self, job_id, step_key, body):
        await require_runtime(self.session, self.settings, worker=True)
        response = await self.jobs.prepare(job_id, step_key, body)
        if response["writeAllowed"]:
            job = await self.repository.get(job_id)
            step = await self.jobs.step(job_id, step_key)
            material = await self.authorization.access(job)
            require(material.access_revision == body.access_revision, "本人授权已变化")
            data = step.input_json
            if step.kind == "create_bug":
                tool, arguments = "post_bugs", {"payload": data["payload"]}
            elif step.kind == "upload_attachment":
                file = await self.pushes.bugs.files.accessible(job.actor_user_id, data["fileId"])
                ticket = await self.pushes.bugs.files.ticket(file)
                tool, arguments = (
                    "upload_bug_attachment",
                    {
                        "bugId": job.mapping_json["remoteBugId"],
                        "filename": file.filename,
                        "contentType": file.content_type,
                        "size": file.size,
                        "sha256": file.sha256,
                        "downloadUrl": ticket["url"],
                    },
                )
            else:
                tool, arguments = (
                    "put_bugs_bugID",
                    {
                        "bugID": job.mapping_json["remoteBugId"],
                        "payload": {"steps": data["desiredSteps"]}
                        if step.kind == "update_description"
                        else data["payload"],
                    },
                )
            response.update(
                access={"endpoint": material.endpoint, "token": material.token.get_secret_value()},
                operation={
                    "tool": tool,
                    "arguments": arguments,
                    "timeoutSeconds": 180 if step.kind == "upload_attachment" else 30,
                },
            )
        await self.session.commit()
        return response

    @local_transaction
    async def result(self, job_id, step_key, body, *, evidence=False):
        await require_runtime(self.session, self.settings, worker=True)
        response = await self.jobs.result(job_id, step_key, body, evidence=evidence)
        await self.session.commit()
        return response

    @local_transaction
    async def failure(self, job_id, step_key, body):
        await require_runtime(self.session, self.settings, worker=True)
        response = await self.jobs.preflight_failure(job_id, step_key, body)
        await self.session.commit()
        return response

    @local_transaction
    async def completed(self, job_id, identity):
        await require_runtime(self.session, self.settings, worker=True)
        job = await self.jobs.locked(job_id)
        require(
            job.worker_id == identity.worker_id
            and job.claim_generation == identity.claim_generation
            and job.runtime_generation == identity.runtime_generation
            and job.runtime_generation == self.jobs.runtime_generation,
            "任务领取身份已失效",
        )
        if job.status in {"claimed", "running"}:
            await self.jobs.owned(job_id, identity)
            await self.jobs.finish(job)
        await self.session.commit()
        return summary(job)
