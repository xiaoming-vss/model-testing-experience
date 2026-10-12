"""Local queue commands. The caller commits once with any related domain changes.

Authorization and domain result application are injected by the Bug integration coordinator.
No command makes remote calls; failed commands must roll back the request transaction.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from testing_agent.core.errors import AppError, ErrNotFound
from testing_agent.domain.integration_execution import (
    ACTIVE_JOB_STATUSES,
    SUCCESS_STEP_STATUSES,
    UNRESOLVED_STEP_STATUSES,
    JobStatus,
    StepStatus,
    aggregate,
    digest,
    require_safe_snapshot,
    same_result,
    utc,
)
from testing_agent.models.integration_job import (
    IntegrationClaimReceipt,
    IntegrationJob,
    IntegrationJobStep,
)
from testing_agent.repositories.integration_job import IntegrationJobRepository
from testing_agent.schemas.integration_job import (
    IntegrationClaimRequest,
    IntegrationFailureRequest,
    IntegrationPrepareRequest,
    IntegrationRemoteResult,
    IntegrationResultRequest,
    IntegrationSubmission,
    IntegrationWorkerIdentity,
)

Authorize = Callable[[IntegrationJob], Awaitable[None]]
ApplyResult = Callable[[IntegrationJob, IntegrationJobStep, bool], Awaitable[None]]
ValidatePrepare = Callable[
    [IntegrationJob, IntegrationJobStep, IntegrationPrepareRequest], Awaitable[None]
]
LockResource = Callable[[str], Awaitable[None]]
PrepareDomain = Callable[[IntegrationJob, IntegrationJobStep], Awaitable[None]]
SyncDomain = Callable[[IntegrationJob], Awaitable[None]]


async def no_change(*args: Any) -> None:
    pass


def conflict(message: str) -> AppError:
    return AppError(409, message, 409)


def summary(job: IntegrationJob) -> dict[str, Any]:
    return {
        "jobId": job.job_id,
        "jobStatus": job.status,
        "taskType": job.task_type,
        "protocolVersion": job.protocol_version,
        "result": {"steps": job.result_json.get("steps", {})},
    }


class IntegrationJobService:
    def __init__(
        self,
        repository: IntegrationJobRepository,
        *,
        authorize: Authorize,
        validate_prepare: ValidatePrepare,
        apply_result: ApplyResult,
        runtime_generation: str,
        lease_seconds: int = 60,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        lock_resource: LockResource | None = None,
        on_prepare: PrepareDomain | None = None,
        on_state: SyncDomain | None = None,
    ):
        if not runtime_generation or not 10 <= lease_seconds <= 600:
            raise ValueError("Invalid integration runtime or lease")
        self.repository = repository
        self.authorize = authorize
        self.validate_prepare = validate_prepare
        self.apply_result = apply_result
        self.runtime_generation = runtime_generation
        self.lease_seconds = lease_seconds
        self.clock = clock
        self.lock_resource = lock_resource or no_change
        self.on_prepare = on_prepare or no_change
        self.on_state = on_state or no_change

    async def submit(self, body: IntegrationSubmission) -> IntegrationJob:
        await self.lock_resource(body.project_id)
        payload = body.model_dump(mode="json", by_alias=True)
        require_safe_snapshot(payload)
        request_digest = digest(payload)
        quarantined = await self.repository.session.scalar(
            select(IntegrationJob.job_id)
            .where(
                IntegrationJob.bug_id == body.bug_id,
                IntegrationJob.recovery_required.is_(True),
            )
            .limit(1)
        )
        if quarantined is not None:
            raise conflict("该 Bug 有恢复隔离任务，请完成外部核对后再发起操作")
        existing = await self.repository.by_request(body.actor_user_id, body.request_id)
        if existing is not None:
            if existing.request_digest != request_digest:
                raise conflict("相同请求编号对应不同集成操作")
            return existing
        keys = [step.step_key for step in body.steps]
        seen: set[str] = set()
        if len(set(keys)) != len(keys):
            raise conflict("步骤编号重复")
        for step in body.steps:
            if not set(step.dependencies).issubset(seen):
                raise conflict("步骤依赖必须引用前面的步骤")
            seen.add(step.step_key)
        job = IntegrationJob(
            job_id=uuid4().hex,
            protocol_version=1,
            task_type=body.task_type,
            project_id=body.project_id,
            bug_id=body.bug_id,
            actor_user_id=body.actor_user_id,
            service_id=body.service_id,
            connection_id=body.connection_id,
            target_key=body.target_key,
            runtime_generation=self.runtime_generation,
            request_id=body.request_id,
            request_digest=request_digest,
            input_revision=body.input_revision,
            target_revision=body.target_revision,
            snapshot_json=body.snapshot,
            mapping_json=body.mapping,
            result_json={},
            active_scope=digest([body.project_id, body.bug_id]),
            status=JobStatus.QUEUED,
        )
        await self.authorize(job)
        try:
            async with self.repository.session.begin_nested():
                self.repository.add(job)
                await self.repository.flush()
                for step in body.steps:
                    self.repository.add(
                        IntegrationJobStep(
                            job_id=job.job_id,
                            step_key=step.step_key,
                            kind=step.kind,
                            dependencies_json=step.dependencies,
                            input_json=step.input,
                            status=StepStatus.PENDING,
                        )
                    )
                await self.repository.flush()
        except IntegrityError as exc:
            existing = await self.repository.by_request(
                body.actor_user_id, body.request_id, lock=True
            )
            if existing is not None and existing.request_digest == request_digest:
                return existing
            raise conflict("该 Bug 已有活跃集成任务或请求编号冲突") from exc
        return job

    async def claim(self, body: IntegrationClaimRequest, *, enabled: bool = True) -> dict[str, Any]:
        key = digest([body.worker_id, body.claim_request_id])
        request_digest = digest(body.model_dump(mode="json", by_alias=True))
        receipt = await self.repository.claim_receipt(key)
        if receipt is not None:
            if receipt.request_digest != request_digest:
                raise conflict("领取请求编号不能用于不同能力声明")
            return receipt.response_json
        receipt = IntegrationClaimReceipt(
            claim_key=key,
            request_id=body.claim_request_id,
            request_digest=request_digest,
            response_json={"job": None},
        )
        try:
            async with self.repository.session.begin_nested():
                self.repository.add(receipt)
                await self.repository.flush()
        except IntegrityError:
            receipt = await self.repository.claim_receipt(key, lock=True)
            if receipt is None or receipt.request_digest != request_digest:
                raise conflict("领取请求冲突") from None
            return receipt.response_json
        if not enabled:
            return receipt.response_json
        excluded: list[int] = []
        for _ in range(100):
            job = await self.repository.candidate(
                body.protocol_versions, body.task_types, excluded, lock=False
            )
            if job is None:
                break
            excluded.append(job.id)
            await self.lock_resource(job.project_id)
            job = await self.repository.get(job.job_id, lock=True, skip_locked=True)
            if job is None or job.status != JobStatus.QUEUED:
                continue
            if job.runtime_generation != self.runtime_generation:
                await self.cancel(job, "canceled")
                continue
            try:
                await self.authorize(job)
            except AppError as exc:
                if exc.http_code not in (403, 404):
                    raise
                await self.cancel(job, "access_revoked")
                continue
            if await self.repository.target_busy(job.target_key):
                continue
            # The nullable unique target constraint coordinates concurrent CP/Worker replicas.
            try:
                async with self.repository.session.begin_nested():
                    now = self.clock()
                    job.active_target = job.target_key
                    job.status = JobStatus.CLAIMED
                    job.worker_id = body.worker_id
                    job.claim_key = key
                    job.claim_generation += 1
                    job.heartbeat_at = now
                    if job.first_claimed_at is None:
                        job.first_claimed_at = now
                        waited = (now - utc(job.created_at)).total_seconds()
                        job.queue_wait_ms = round(waited * 1000) if waited >= 0 else None
                    job.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
                    await self.repository.flush()
            except IntegrityError:
                continue
            response = {
                "job": {
                    **summary(job),
                    "workerId": job.worker_id,
                    "claimGeneration": job.claim_generation,
                    "runtimeGeneration": job.runtime_generation,
                    "leaseSeconds": self.lease_seconds,
                }
            }
            receipt.job_id = job.job_id
            receipt.response_json = response
            return response
        return receipt.response_json

    async def owned(self, job_id: str, identity: IntegrationWorkerIdentity) -> IntegrationJob:
        job = await self.locked(job_id)
        if job is None:
            raise ErrNotFound()
        if (
            job.worker_id != identity.worker_id
            or job.claim_generation != identity.claim_generation
            or job.runtime_generation != identity.runtime_generation
            or job.runtime_generation != self.runtime_generation
        ):
            raise conflict("任务领取身份或运行代次已失效")
        if (
            job.status not in (JobStatus.CLAIMED, JobStatus.RUNNING)
            or job.lease_expires_at is None
            or utc(job.lease_expires_at) <= self.clock()
        ):
            raise conflict("任务租约已失效")
        await self.authorize(job)
        return job

    async def locked(self, job_id: str) -> IntegrationJob:
        job = await self.repository.get(job_id)
        if job is None:
            raise ErrNotFound()
        await self.lock_resource(job.project_id)
        job = await self.repository.get(job_id, lock=True)
        if job is None:
            raise ErrNotFound()
        if job.recovery_required:
            raise conflict("该任务处于恢复隔离，不能领取、回传或重新执行")
        return job

    async def heartbeat(self, job_id: str, identity: IntegrationWorkerIdentity) -> dict[str, Any]:
        job = await self.owned(job_id, identity)
        now = self.clock()
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
        return {"jobId": job.job_id, "leaseSeconds": self.lease_seconds}

    async def input(self, job_id: str, identity: IntegrationWorkerIdentity) -> dict[str, Any]:
        job = await self.owned(job_id, identity)
        return {
            **summary(job),
            "snapshot": job.snapshot_json,
            "mapping": job.mapping_json,
            "inputRevision": job.input_revision,
            "targetRevision": job.target_revision,
            "steps": [
                {
                    "stepKey": s.step_key,
                    "kind": s.kind,
                    "status": s.status,
                    "dependencies": s.dependencies_json,
                    "input": s.input_json,
                }
                for s in await self.repository.steps(job_id)
            ],
        }

    async def step(self, job_id: str, step_key: str) -> IntegrationJobStep:
        for step in await self.repository.steps(job_id, lock=True):
            if step.step_key == step_key:
                return step
        raise ErrNotFound()

    async def prepare(
        self, job_id: str, step_key: str, body: IntegrationPrepareRequest
    ) -> dict[str, Any]:
        job = await self.locked(job_id)
        step = await self.step(job_id, step_key)
        if step.status != StepStatus.PENDING:
            # A lost prepare response never grants a second write permit.
            if (
                job.runtime_generation != body.runtime_generation
                or job.runtime_generation != self.runtime_generation
                or step.intent_worker_id != body.worker_id
                or step.intent_generation != body.claim_generation
                or step.prepare_request_id != body.prepare_request_id
            ):
                raise conflict("预约不属于该领取者的原请求")
            return {"operationId": step.operation_id, "status": step.status, "writeAllowed": False}
        job = await self.owned(job_id, body)
        require_safe_snapshot(body.input)
        if job.input_revision != body.input_revision or job.target_revision != body.target_revision:
            raise conflict("集成输入或目标已变化")
        states = {s.step_key: s.status for s in await self.repository.steps(job_id)}
        if any(states[key] not in SUCCESS_STEP_STATUSES for key in step.dependencies_json):
            raise conflict("依赖步骤尚未成功")
        await self.validate_prepare(job, step, body)
        step.input_json = body.input
        step.operation_id = uuid4().hex
        step.prepare_request_id = body.prepare_request_id
        step.intent_worker_id = body.worker_id
        step.intent_generation = body.claim_generation
        if body.decision != "write":
            step.status = StepStatus.NOOP if body.decision == "noop" else StepStatus.FAILED
            step.result_json = IntegrationRemoteResult.model_validate(
                body.input.get("result", {})
            ).model_dump(mode="json", by_alias=True, exclude_none=True)
            await self.apply_result(job, step, False)
            await self.finish(job)
            await self.repository.flush()
            return {
                "operationId": step.operation_id,
                "status": step.status,
                "writeAllowed": False,
                "mapping": job.mapping_json,
                **summary(job),
            }
        step.status = StepStatus.WRITE_INTENT
        step.permit_expires_at = job.lease_expires_at
        job.status = JobStatus.RUNNING
        await self.on_prepare(job, step)
        await self.repository.flush()
        assert step.permit_expires_at is not None
        return {
            "operationId": step.operation_id,
            "status": step.status,
            "writeAllowed": True,
            "permitSeconds": max(0, (utc(step.permit_expires_at) - self.clock()).total_seconds()),
        }

    async def result(
        self, job_id: str, step_key: str, body: IntegrationResultRequest, *, evidence: bool = False
    ) -> dict[str, Any]:
        job = await self.locked(job_id)
        step = await self.step(job_id, step_key)
        if (
            job.runtime_generation != body.runtime_generation
            or job.runtime_generation != self.runtime_generation
            or step.operation_id != body.operation_id
            or step.intent_worker_id != body.worker_id
            or step.intent_generation != body.claim_generation
        ):
            raise conflict("结果不属于该任务的原写入意图")
        payload = body.model_dump(mode="json", by_alias=True)
        if body.remote_duration_ms is None:
            payload.pop("remoteDurationMs", None)  # Preserve pre-observation receipt digests.
        event_digest = digest(payload)
        for receipt in step.receipts_json:
            if receipt["eventId"] == body.event_id:
                if receipt["digest"] != event_digest:
                    raise conflict("相同结果事件对应不同内容")
                return receipt["response"]
        if job.archived_at is not None:
            raise conflict("该执行历史已清理，仅允许查询原结果回执")
        if (
            evidence
            and step.status == StepStatus.SUCCEEDED
            and body.status == "succeeded"
            and same_result(
                step.kind,
                step.result_json,
                body.result.model_dump(mode="json", by_alias=True, exclude_none=True),
            )
        ):
            # A trusted read-only recovery can precede the original Worker's outbox replay.
            # Acknowledge matching facts without applying the domain result or activity again.
            if step.remote_duration_ms is None and body.remote_duration_ms is not None:
                step.remote_duration_ms, step.remote_recorded_at = (
                    body.remote_duration_ms,
                    self.clock(),
                )
            return await self.result_receipt(job, step, body.event_id, event_digest)
        if not evidence:
            await self.owned(job_id, body)
        if step.status not in UNRESOLVED_STEP_STATUSES:
            raise conflict("已明确的步骤结果不能被覆盖")
        if evidence and step.status != StepStatus.UNKNOWN:
            raise conflict("晚到证据只允许核对原未知步骤")
        step.status = body.status
        if step.remote_duration_ms is None and body.remote_duration_ms is not None:
            step.remote_duration_ms, step.remote_recorded_at = body.remote_duration_ms, self.clock()
        step.result_json = body.result.model_dump(mode="json", by_alias=True, exclude_none=True)
        await self.apply_result(job, step, evidence)
        await self.finish(job)
        return await self.result_receipt(job, step, body.event_id, event_digest)

    async def result_receipt(self, job, step, event_id: str, event_digest: str):
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
                "eventId": event_id,
                "digest": event_digest,
                "response": response,
            },
        ]
        await self.repository.flush()
        return response

    async def without_write(
        self, job: IntegrationJob, step_key: str, status: str, *, reason: str
    ) -> None:
        """Trusted coordinator applies verified no-op, preflight failure or dependency blocking."""
        if status not in (StepStatus.NOOP, StepStatus.FAILED, StepStatus.BLOCKED):
            raise ValueError("Invalid pre-write outcome")
        step = await self.step(job.job_id, step_key)
        if step.status != StepStatus.PENDING:
            raise conflict("已有写入意图的步骤不能按未执行处理")
        step.status = status
        step.result_json = {"reason": reason}
        await self.finish(job)

    async def finish(self, job: IntegrationJob) -> None:
        steps = await self.repository.steps(job.job_id, lock=True)
        now = self.clock()
        for step in steps:
            if step.status == StepStatus.FAILED and step.failed_at is None:
                step.failed_at = now
            if step.status == StepStatus.UNKNOWN and step.unknown_at is None:
                step.unknown_at = now
            error = step.result_json.get("errorCode", step.result_json.get("reason"))
            if error == "lease_lost" and step.lease_lost_at is None:
                step.lease_lost_at = now
            if error == "access_revoked" and step.access_revoked_at is None:
                step.access_revoked_at = now
        states = {s.step_key: s.status for s in steps}
        for step in steps:
            if step.status == StepStatus.PENDING and any(
                states[key] in (StepStatus.FAILED, StepStatus.BLOCKED, StepStatus.CANCELED)
                for key in step.dependencies_json
            ):
                step.status = StepStatus.BLOCKED
                step.result_json = {"reason": "dependency_failed"}
                states[step.step_key] = step.status
        if StepStatus.UNKNOWN in states.values():
            for step in steps:
                if step.status == StepStatus.PENDING:
                    step.status = StepStatus.BLOCKED
                    step.result_json = {"reason": "unresolved_write"}
                    states[step.step_key] = step.status
        job.status = aggregate(list(states.values()), canceled=job.canceled_at is not None)
        job.result_json = {**job.result_json, "steps": states}
        if job.status not in ACTIVE_JOB_STATUSES:
            job.active_scope = None
            job.active_target = None
            job.lease_expires_at = None
            job.finished_at = self.clock()
        await self.on_state(job)

    async def preflight_failure(
        self, job_id: str, step_key: str, body: IntegrationFailureRequest
    ) -> dict[str, Any]:
        job = await self.locked(job_id)
        step = await self.step(job_id, step_key)
        event_digest = digest(body.model_dump(mode="json", by_alias=True))
        for receipt in step.receipts_json:
            if receipt["eventId"] == body.event_id:
                if receipt["digest"] != event_digest:
                    raise conflict("相同结果事件对应不同内容")
                if (
                    job.runtime_generation != body.runtime_generation
                    or job.runtime_generation != self.runtime_generation
                ):
                    raise conflict("任务运行代次已失效")
                return receipt["response"]
        job = await self.owned(job_id, body)
        if step.status != StepStatus.PENDING or step.operation_id:
            raise conflict("已有写入意图的步骤不能按未执行处理")
        step.status = StepStatus.FAILED
        step.result_json = {"errorCode": body.error_code}
        await self.finish(job)
        response = {**summary(job), "stepKey": step.step_key, "status": step.status}
        step.receipts_json = [
            *step.receipts_json,
            {
                "eventId": body.event_id,
                "digest": event_digest,
                "response": response,
            },
        ]
        await self.repository.flush()
        return response

    async def cancel(self, job: IntegrationJob, reason: str) -> None:
        job.canceled_at = self.clock()
        for step in await self.repository.steps(job.job_id, lock=True):
            if step.status == StepStatus.WRITE_INTENT:
                step.status = StepStatus.UNKNOWN
                step.result_json = {"errorCode": reason}
            elif step.status == StepStatus.PENDING:
                step.status = StepStatus.CANCELED
                step.result_json = {"reason": reason}
        job.status = JobStatus.CANCELED
        await self.finish(job)

    async def expire(self) -> int:
        jobs = await self.repository.expired(self.clock(), lock=False)
        expired = 0
        for candidate in jobs:
            job = await self.locked(candidate.job_id)
            if (
                job.status not in {JobStatus.CLAIMED, JobStatus.RUNNING}
                or job.lease_expires_at is None
                or utc(job.lease_expires_at) > self.clock()
            ):
                continue
            expired += 1
            steps = await self.repository.steps(job.job_id, lock=True)
            if any(s.status in UNRESOLVED_STEP_STATUSES for s in steps):
                for step in steps:
                    if step.status == StepStatus.WRITE_INTENT:
                        step.status = StepStatus.UNKNOWN
                        step.result_json = {"errorCode": "lease_lost"}
                await self.finish(job)
            elif any(s.status == StepStatus.PENDING for s in steps):
                job.status = JobStatus.QUEUED
                job.active_target = None
                job.lease_expires_at = None
                job.claim_key = None
            else:
                await self.finish(job)
        return expired

    async def revoke(self, **filters: str) -> int:
        if not filters:
            raise ValueError("Revocation requires a resource scope")
        jobs = await self.repository.matching(**filters, lock=False)
        revoked = 0
        for candidate in jobs:
            job = await self.locked(candidate.job_id)
            if job.status in ACTIVE_JOB_STATUSES:
                await self.cancel(job, "access_revoked")
                revoked += 1
        return revoked
