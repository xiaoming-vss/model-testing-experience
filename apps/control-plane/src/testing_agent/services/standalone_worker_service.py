"""Worker lease operations for an independent multi-stage dispatch.

WorkerTask is locked by the caller before invoking these methods. The service
commits queue and execution changes together, matching the Worker API boundary.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.enums import RUN_TERMINAL_STATUSES
from testing_agent.core.errors import AppError, ErrBadRequest, ErrForbidden
from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.worker_task import WorkerTask
from testing_agent.schemas.workers import (
    WorkerClaimRequest,
    WorkerProgressRequest,
    WorkerTaskEventRequest,
)
from testing_agent.services.standalone_worker_authorization import (
    StandaloneWorkerAuthority,
    authorize_standalone_worker,
)
from testing_agent.services.standalone_worker_events import (
    apply_standalone_completion,
    apply_standalone_progress,
)
from testing_agent.services.standalone_worker_payload import standalone_worker_payloads
from testing_agent.services.standalone_worker_transitions import StandaloneWorkerTransitions
from testing_agent.services.worker_domains.events import apply_event_to_task, update_task_claimed
from testing_agent.services.worker_domains.guard import ensure_task_id, ensure_worker_match


class StandaloneWorkerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.transitions = StandaloneWorkerTransitions(session)

    async def is_standalone(self, queue: WorkerTask) -> bool:
        if not isinstance(queue, WorkerTask) or queue.domain != "ai":
            return False
        return bool(
            await self.session.scalar(
                select(AiExecution.execution_id)
                .join(
                    AiGenerationAttempt,
                    AiGenerationAttempt.execution_id == AiExecution.execution_id,
                )
                .where(
                    AiGenerationAttempt.id == queue.run_id,
                    AiExecution.workflow_status.is_not(None),
                )
            )
        )

    async def authorize(
        self, queue: WorkerTask, *, pending: bool = False
    ) -> StandaloneWorkerAuthority:
        try:
            return await authorize_standalone_worker(self.session, queue, pending=pending)
        except AppError as exc:
            if queue.status in {"pending", "claimed", "running"}:
                await self.retire(
                    queue, "操作人的项目访问或个人授权已失效，请配置本人授权后重新执行"
                )
                await self.session.commit()
            raise ErrForbidden() from exc

    async def retire(self, queue: WorkerTask, message: str) -> None:
        """Retire only this still-current dispatch, without modifying earlier results."""
        task = await self.session.scalar(
            select(AiGenerateTask)
            .join(AiExecution, AiExecution.task_id == AiGenerateTask.task_id)
            .join(AiGenerationAttempt, AiGenerationAttempt.execution_id == AiExecution.execution_id)
            .where(
                AiGenerationAttempt.id == queue.run_id,
                AiGenerationAttempt.worker_task_id == queue.task_id,
                AiExecution.workflow_status.is_not(None),
                AiGenerateTask.task_type == queue.task_type,
            )
        )
        if task is not None:
            try:
                await self.transitions.failed(task, queue, status="failed", error_message=message)
            except type(ErrBadRequest):
                pass  # A newer dispatch or a terminal execution must remain unchanged.
        queue.status = "failed"
        queue.error_message = message
        queue.finished_at = datetime.now(UTC)
        queue.lease_expires_at = queue.finished_at

    async def claim(self, queue: WorkerTask, body: WorkerClaimRequest) -> dict[str, Any]:
        authority = await self.authorize(queue, pending=True)
        await self.transitions.claimed(authority.task, queue)
        await update_task_claimed(queue, body)
        claim, _ = standalone_worker_payloads(authority, queue, lease_seconds=30)
        await self.session.commit()
        return claim

    async def snapshot(self, queue: WorkerTask) -> dict[str, Any]:
        authority = await self.authorize(queue)
        _, snapshot = standalone_worker_payloads(authority, queue, lease_seconds=30)
        return snapshot

    async def started(self, queue: WorkerTask, body: WorkerTaskEventRequest) -> dict[str, Any]:
        ensure_worker_match(queue, body.worker_id)
        ensure_task_id(queue, body)
        if body.run_id and body.run_id != queue.run_id:
            raise ErrBadRequest()
        if queue.status in RUN_TERMINAL_STATUSES:
            # A late start must not reopen a run that already finished.
            return {"taskId": queue.task_id, "workerId": body.worker_id}
        authority = await self.authorize(queue)
        await self.transitions.started(authority.task, queue)
        await apply_event_to_task(queue, body, "running")
        await self.session.commit()
        return {"taskId": queue.task_id, "workerId": body.worker_id}

    async def heartbeat(self, queue: WorkerTask, body: WorkerTaskEventRequest) -> dict[str, Any]:
        ensure_worker_match(queue, body.worker_id)
        ensure_task_id(queue, body)
        if body.run_id and body.run_id != queue.run_id:
            raise ErrBadRequest()
        if queue.status in RUN_TERMINAL_STATUSES:
            # A late heartbeat must not rewrite finished_at or extend the lease.
            return {"taskId": queue.task_id, "workerId": body.worker_id}
        authority = await self.authorize(queue)
        await self.transitions.current(authority.task, queue)
        await apply_event_to_task(queue, body, queue.status)
        await self.session.commit()
        return {"taskId": queue.task_id, "workerId": body.worker_id}

    async def progress(self, queue: WorkerTask, body: WorkerProgressRequest) -> dict[str, Any]:
        ensure_worker_match(queue, body.worker_id)
        authority = await self.authorize(queue)
        async with self.session.begin_nested():
            finished = await apply_standalone_progress(self.session, authority.task, queue, body)
            now = datetime.now(UTC)
            queue.heartbeat_at = now
            if finished:
                queue.status = "success"
                queue.finished_at = queue.lease_expires_at = now
            else:
                queue.lease_expires_at = now + timedelta(seconds=30)
        await self.session.commit()
        return {"taskId": queue.task_id}

    async def complete(self, queue: WorkerTask, body: WorkerTaskEventRequest) -> dict[str, Any]:
        ensure_worker_match(queue, body.worker_id)
        ensure_task_id(queue, body)
        authority = await self.authorize(queue)
        async with self.session.begin_nested():
            status = await apply_standalone_completion(self.session, authority.task, queue, body)
            queue.status = status
            queue.finished_at = queue.lease_expires_at = datetime.now(UTC)
        await self.session.commit()
        return {"taskId": queue.task_id, "workerId": body.worker_id, "status": status}
