"""Worker service for direct stage attempts."""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.enums import RUN_TERMINAL_STATUSES
from testing_agent.core.errors import AppError, ErrBadRequest, ErrForbidden, ErrNotFound
from testing_agent.domain.ai_tasks import AUXILIARY_EXECUTION_TYPES
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.worker_task import WorkerTask
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.schemas.workers import (
    WorkerClaimRequest,
    WorkerProgressRequest,
    WorkerTaskEventRequest,
)
from testing_agent.services.stage_storage.authorization import authorize_stage_worker
from testing_agent.services.stage_storage.payload import worker_payloads
from testing_agent.services.stage_storage.worker import StageWorkerTransitions
from testing_agent.services.stage_storage.worker_events import (
    apply_auxiliary_completion,
    apply_auxiliary_progress,
    apply_stage_completion,
    apply_stage_progress,
)
from testing_agent.services.worker_domains.events import apply_event_to_task, update_task_claimed


def _design_kind(task_type: str) -> DesignKind:
    mapping = {
        "requirement_analysis": "requirement_analysis",
        "functional_case_generate": "function",
        "api_case_generate": "api",
        "ui_case_generate": "ui",
    }
    if task_type not in mapping:
        raise ErrBadRequest()
    return cast(DesignKind, mapping[task_type])


class DirectStageWorkerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.transitions = StageWorkerTransitions(session)

    async def is_direct(self, task: WorkerTask) -> bool:
        """A run identity matching an attempt is handled here, even on mismatched queue IDs."""
        if not isinstance(task, WorkerTask) or task.domain != "ai":
            return False
        return bool(
            await self.session.scalar(
                select(AiGenerationAttempt.id).where(AiGenerationAttempt.id == task.run_id)
            )
        )

    async def _stage(self, stage_id: str) -> AiGenerationStage:
        stage = await self.session.scalar(
            select(AiGenerationStage).where(AiGenerationStage.id == stage_id)
        )
        if stage is None:
            raise ErrNotFound()
        return stage

    async def authorize(self, task: WorkerTask, *, pending: bool = False):
        try:
            return await authorize_stage_worker(self.session, task, pending=pending)
        except AppError as exc:
            if task.status in {"pending", "claimed", "running"}:
                await self.fail_authorization(task)
            raise ErrForbidden() from exc

    async def fail_authorization(self, task: WorkerTask) -> None:
        """Retire a queued task after an actor loses access and commit the worker event."""
        await self.retire_authorization(task)
        await self.session.commit()

    async def retire_authorization(self, task: WorkerTask) -> None:
        """Retire a task inside the caller's transaction, preserving approved versions."""
        message = "操作人的项目访问或个人授权已失效，请配置本人授权后重新执行"
        attempt = await self.session.scalar(
            select(AiGenerationAttempt).where(
                AiGenerationAttempt.id == task.run_id,
                AiGenerationAttempt.worker_task_id == task.task_id,
            )
        )
        if attempt is not None:
            try:
                await self.transitions.failed(
                    attempt.stage_id, attempt.id, task.task_id, error_message=message
                )
            except type(ErrBadRequest):
                pass  # An obsolete task cannot change the currently active attempt.
        task.status = "failed"
        task.error_message = message
        task.finished_at = datetime.now(UTC)
        task.lease_expires_at = task.finished_at

    async def expire(self, task: WorkerTask) -> None:
        """Expire only the queue's still-current stage attempt; caller commits."""
        attempt = await self.session.scalar(
            select(AiGenerationAttempt).where(
                AiGenerationAttempt.id == task.run_id,
                AiGenerationAttempt.worker_task_id == task.task_id,
            )
        )
        message = "Worker 心跳超时，执行已终止，请重试"
        if attempt is not None:
            try:
                await self.transitions.failed(
                    attempt.stage_id, attempt.id, task.task_id, error_message=message
                )
            except type(ErrBadRequest):
                pass
        task.status = "failed"
        task.error_message = message
        task.finished_at = datetime.now(UTC)
        task.lease_expires_at = task.finished_at

    async def claim(self, task: WorkerTask, body: WorkerClaimRequest) -> dict[str, Any]:
        authority = await self.authorize(task, pending=True)
        stage, attempt = await self.transitions.current(
            authority.stage_id, authority.attempt_id, task.task_id
        )
        await update_task_claimed(task, body)
        attempt.status = "claimed"
        task.lease_expires_at = datetime.now(UTC) + timedelta(seconds=30)
        claim, _ = worker_payloads(authority, task, stage_name=stage.stage, lease_seconds=30)
        await self.session.commit()
        return claim

    async def snapshot(self, task: WorkerTask) -> dict[str, Any]:
        authority = await self.authorize(task)
        stage = await self._stage(authority.stage_id)
        _, snapshot = worker_payloads(authority, task, stage_name=stage.stage, lease_seconds=30)
        return snapshot

    async def started(self, task: WorkerTask, body: WorkerTaskEventRequest) -> dict[str, Any]:
        from testing_agent.services.worker_domains.guard import ensure_task_id, ensure_worker_match

        ensure_worker_match(task, body.worker_id)
        ensure_task_id(task, body)
        if body.run_id and body.run_id != task.run_id:
            raise ErrBadRequest()
        if task.status in RUN_TERMINAL_STATUSES:
            # A late start must not reopen a run that already finished.
            return {"taskId": task.task_id, "workerId": body.worker_id}
        authority = await self.authorize(task)
        await self.transitions.started(authority.stage_id, authority.attempt_id, task.task_id)
        await apply_event_to_task(task, body, "running")
        await self.session.commit()
        return {"taskId": task.task_id, "workerId": body.worker_id}

    async def heartbeat(self, task: WorkerTask, body: WorkerTaskEventRequest) -> dict[str, Any]:
        from testing_agent.services.worker_domains.guard import ensure_task_id, ensure_worker_match

        ensure_worker_match(task, body.worker_id)
        ensure_task_id(task, body)
        if body.run_id and body.run_id != task.run_id:
            raise ErrBadRequest()
        if task.status in RUN_TERMINAL_STATUSES:
            # A late heartbeat must not rewrite finished_at or extend the lease.
            return {"taskId": task.task_id, "workerId": body.worker_id}
        authority = await self.authorize(task)
        await self.transitions.current(authority.stage_id, authority.attempt_id, task.task_id)
        await apply_event_to_task(task, body, task.status)
        await self.session.commit()
        return {"taskId": task.task_id, "workerId": body.worker_id}

    async def progress(self, task: WorkerTask, body: WorkerProgressRequest) -> dict[str, Any]:
        from testing_agent.services.worker_domains.guard import ensure_worker_match

        ensure_worker_match(task, body.worker_id)
        if body.task_id and body.task_id != task.task_id:
            raise ErrBadRequest()
        authority = await self.authorize(task)
        stage = await self._stage(authority.stage_id)
        snapshot = authority.input_snapshot
        source, config = snapshot.get("source") or {}, snapshot.get("config") or {}
        if not isinstance(source, dict) or not isinstance(config, dict):
            raise ErrBadRequest()
        if task.task_type in AUXILIARY_EXECUTION_TYPES:
            await apply_auxiliary_progress(
                self.session, task, stage_id=stage.id, attempt_id=authority.attempt_id, body=body
            )
        else:
            await apply_stage_progress(
                self.session,
                task,
                stage_id=stage.id,
                attempt_id=authority.attempt_id,
                kind=_design_kind(task.task_type),
                stage=stage.stage,
                source=source,
                frozen_config=config,
                body=body,
            )
        if task.status != "success":
            task.heartbeat_at = datetime.now(UTC)
            task.lease_expires_at = task.heartbeat_at + timedelta(seconds=30)
        await self.session.commit()
        return {"taskId": task.task_id}

    async def complete(self, task: WorkerTask, body: WorkerTaskEventRequest) -> dict[str, Any]:
        from testing_agent.services.worker_domains.guard import ensure_task_id, ensure_worker_match

        ensure_worker_match(task, body.worker_id)
        ensure_task_id(task, body)
        authority = await self.authorize(task)
        stage = await self._stage(authority.stage_id)
        snapshot = authority.input_snapshot
        source, config = snapshot.get("source") or {}, snapshot.get("config") or {}
        if not isinstance(source, dict) or not isinstance(config, dict):
            raise ErrBadRequest()
        if task.task_type in AUXILIARY_EXECUTION_TYPES:
            await apply_auxiliary_completion(
                self.session, task, stage_id=stage.id, attempt_id=authority.attempt_id, body=body
            )
        else:
            await apply_stage_completion(
                self.session,
                task,
                stage_id=stage.id,
                attempt_id=authority.attempt_id,
                kind=_design_kind(task.task_type),
                stage=stage.stage,
                source=source,
                frozen_config=config,
                body=body,
            )
        await self.session.commit()
        return {"taskId": task.task_id, "workerId": body.worker_id, "status": task.status}
