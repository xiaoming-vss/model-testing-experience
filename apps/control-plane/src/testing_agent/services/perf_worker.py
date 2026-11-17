from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.enums import RUN_TERMINAL_STATUSES, PerfRunStatus
from testing_agent.core.errors import AppError, ErrBadRequest, ErrForbidden, ErrNotFound
from testing_agent.models.stored_file import StoredFile
from testing_agent.repositories.worker_task import WorkerTaskRepository
from testing_agent.schemas.perf_worker import (
    PerfClaimResponse,
    PerfControlResponse,
    PerfHeartbeatResponse,
    PerfResultEvent,
    PerfSnapshotResponse,
)
from testing_agent.schemas.workers import WorkerClaimRequest, WorkerTaskEventRequest
from testing_agent.services.execution_secrets import redact
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.perf_run import read_private_spec
from testing_agent.services.perf_suite_run import (
    on_child_completed_after_commit,
    on_child_started_after_commit,
)
from testing_agent.services.stored_file import StoredFileService
from testing_agent.services.worker import find_task, parse_event_time
from testing_agent.services.worker_authorization import authorize_execution
from testing_agent.services.worker_domains.events import (
    PERF_LEASE_SECONDS,
    apply_event_to_task,
    update_task_claimed,
)
from testing_agent.services.worker_domains.guard import ensure_worker_match
from testing_agent.services.worker_domains.perf import get_run

_MAX_SUMMARY_BYTES = 5 * 1024 * 1024


class PerfWorkerService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        files: StoredFileService,
        credential_cipher: IntegrationCredentialCipher,
    ) -> None:
        self.session = session
        self.files = files
        self.credential_cipher = credential_cipher
        self.repository = WorkerTaskRepository(session)

    async def claim(self, worker_id: str) -> dict[str, Any] | None:
        if not worker_id or not worker_id.strip():
            raise ErrBadRequest()
        task = await self.repository.claim_pending("perf")
        if task is None:
            return None
        try:
            await authorize_execution(self.session, task, pending=True)
        except AppError as exc:
            if exc.http_code == 403:
                return None
            raise
        await update_task_claimed(
            task,
            WorkerClaimRequest(worker_id=worker_id),
            lease_seconds=PERF_LEASE_SECONDS,
        )
        await self.repository.commit()
        response = PerfClaimResponse(
            task_id=task.task_id,
            task_type=task.task_type,
            run_id=task.run_id,
            status=task.status,
            lease_seconds=PERF_LEASE_SECONDS,
        )
        return response.model_dump(by_alias=True)

    async def snapshot(self, task_id: str, worker_id: str) -> dict[str, Any]:
        task = await find_task(self.session, "perf", task_id)
        await authorize_execution(self.session, task)
        ensure_worker_match(task, worker_id)
        run = await get_run(self.session, task)
        if run is None:
            raise ErrNotFound()
        spec, _secrets = read_private_spec(run, self.credential_cipher)
        response = PerfSnapshotResponse(
            task_id=task.task_id,
            run_id=task.run_id,
            case_name=run.case_name,
            run_spec=spec,
            data_files=run.data_files_json or [],
            lease_seconds=PERF_LEASE_SECONDS,
        )
        await self.repository.commit()
        return response.model_dump(by_alias=True)

    @staticmethod
    def _ensure_terminal_worker(task, worker_id: str) -> None:
        if task.worker_id and task.worker_id != worker_id:
            raise ErrForbidden()

    async def started(self, task_id: str, worker_id: str, started_at: str) -> None:
        task = await find_task(self.session, "perf", task_id)
        if task.status in RUN_TERMINAL_STATUSES:
            self._ensure_terminal_worker(task, worker_id)
            await self.repository.commit()
            return
        await authorize_execution(self.session, task)
        ensure_worker_match(task, worker_id)
        if task.status == "stopping":
            await self.repository.commit()
            return
        parsed = parse_event_time(started_at)
        if started_at and parsed is None:
            raise ErrBadRequest()
        now = datetime.now(UTC)
        run = await get_run(self.session, task)
        if run is None:
            raise ErrNotFound()
        if run.status == PerfRunStatus.QUEUED.value:
            run.status = PerfRunStatus.RUNNING.value
        run.started_at = parsed or now
        await apply_event_to_task(
            task,
            WorkerTaskEventRequest(worker_id=worker_id, started_at=started_at),
            "running",
            lease_seconds=PERF_LEASE_SECONDS,
        )
        task.started_at = parsed or now
        await self.repository.commit()
        await on_child_started_after_commit(self.session, task.run_id)

    async def heartbeat(self, task_id: str, worker_id: str) -> dict[str, Any]:
        task = await find_task(self.session, "perf", task_id)
        if task.status in RUN_TERMINAL_STATUSES:
            self._ensure_terminal_worker(task, worker_id)
            await self.repository.commit()
            return PerfHeartbeatResponse(stop_requested=True, lease_seconds=0).model_dump(
                by_alias=True
            )
        await authorize_execution(self.session, task)
        ensure_worker_match(task, worker_id)
        await apply_event_to_task(
            task,
            WorkerTaskEventRequest(worker_id=worker_id),
            task.status,
            lease_seconds=PERF_LEASE_SECONDS,
        )
        await self.repository.commit()
        return PerfHeartbeatResponse(
            stop_requested=task.status == "stopping",
            lease_seconds=PERF_LEASE_SECONDS,
        ).model_dump(by_alias=True)

    async def control(self, task_id: str, worker_id: str) -> dict[str, Any]:
        task = await find_task(self.session, "perf", task_id)
        if task.status in RUN_TERMINAL_STATUSES:
            self._ensure_terminal_worker(task, worker_id)
            await self.repository.commit()
            return PerfControlResponse(stop_requested=True).model_dump(by_alias=True)
        await authorize_execution(self.session, task)
        ensure_worker_match(task, worker_id)
        stop = task.status == "stopping"
        await self.repository.commit()
        return PerfControlResponse(stop_requested=stop).model_dump(by_alias=True)

    async def complete(self, task_id: str, body: PerfResultEvent) -> dict[str, Any]:
        task = await find_task(self.session, "perf", task_id)
        if task.status in RUN_TERMINAL_STATUSES:
            self._ensure_terminal_worker(task, body.worker_id)
            await self.repository.commit()
            await on_child_completed_after_commit(self.session, task.run_id)
            return {"taskId": task_id, "status": task.status}
        await authorize_execution(self.session, task)
        ensure_worker_match(task, body.worker_id)
        if body.run_id and body.run_id != task.run_id:
            raise ErrBadRequest()
        if body.summary is not None:
            try:
                encoded = json.dumps(body.summary, ensure_ascii=False).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise ErrBadRequest() from exc
            if len(encoded) > _MAX_SUMMARY_BYTES:
                raise AppError(400, "summary 不能超过 5MB", 400)
        run = await get_run(self.session, task)
        if run is None:
            raise ErrNotFound()
        _spec, secrets = read_private_spec(run, self.credential_cipher)
        summary = redact(body.summary, secrets) if body.summary is not None else None
        log_tail = redact(body.log_tail, secrets)
        stopping = task.status == "stopping"
        if stopping:
            run_status = PerfRunStatus.CANCELED.value
            task_status = "canceled"
            outcome = "stopped"
            error_message = body.error_message or "用户已停止运行"
        else:
            run_status, task_status, outcome = self._map_status(body)
            error_message = body.error_message
        error_message = redact(error_message, secrets)
        now = datetime.now(UTC)
        started_at = parse_event_time(body.started_at)
        finished_at = parse_event_time(body.finished_at)
        if body.started_at and started_at is None:
            raise ErrBadRequest()
        if body.finished_at and finished_at is None:
            raise ErrBadRequest()
        run.status = run_status
        run.outcome = outcome
        run.summary_json = summary
        run.result_json = body.model_dump(
            by_alias=True, exclude={"summary", "log_tail", "error_message"}
        )
        run.flags_json = body.flags
        run.log_tail = log_tail
        run.error_message = error_message
        run.k6_version = body.k6_version
        run.template_version = body.template_version
        run.script_sha256 = body.script_sha256
        run.runner_json = body.runner
        run.started_at = started_at or run.started_at or now
        run.finished_at = finished_at or now
        run.duration_ms = body.duration_ms
        task.worker_id = body.worker_id
        task.status = task_status
        task.started_at = started_at or task.started_at or now
        task.finished_at = finished_at or now
        task.heartbeat_at = now
        task.lease_expires_at = now
        task.error_message = error_message
        await self.repository.commit()
        await on_child_completed_after_commit(self.session, task.run_id)
        return {"taskId": task_id, "status": task_status}

    def _map_status(self, body: PerfResultEvent) -> tuple[str, str, str]:
        if body.status == "completed":
            if body.outcome not in {"passed", "threshold_failed", "inconclusive"}:
                raise ErrBadRequest()
            return PerfRunStatus.COMPLETED.value, "success", body.outcome
        if body.status == "failed":
            return PerfRunStatus.FAILED.value, "failed", body.outcome
        if body.status == "stopped":
            return PerfRunStatus.STOPPED.value, "canceled", "stopped"
        return PerfRunStatus.CANCELED.value, "canceled", "stopped"

    async def data_file(self, task_id: str, file_id: str, worker_id: str) -> tuple[StoredFile, Any]:
        task = await find_task(self.session, "perf", task_id)
        await authorize_execution(self.session, task)
        ensure_worker_match(task, worker_id)
        run = await get_run(self.session, task)
        if run is None:
            raise ErrNotFound()
        metadata = {
            item.get("fileId"): item
            for item in (run.data_files_json or [])
            if isinstance(item, dict)
        }
        item = metadata.get(file_id)
        if item is None:
            raise ErrNotFound()
        row = await self.files.get(file_id)
        if (
            row.status != "attached"
            or row.purpose != "perf_case_data"
            or row.resource_type != "perf_case"
            or row.resource_id != run.case_id
            or row.project_id != run.project_id
            or row.filename != item.get("filename")
            or row.size != item.get("size")
            or row.sha256 != item.get("sha256")
        ):
            raise ErrNotFound()
        obj = await asyncio.to_thread(self.files.storage.get_object, row.object_key)
        await self.repository.commit()
        return row, obj["Body"]
