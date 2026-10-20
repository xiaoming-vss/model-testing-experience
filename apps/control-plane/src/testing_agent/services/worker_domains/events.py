from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from testing_agent.core.enums import RunStatus
from testing_agent.domain.worker_context import (
    AiWorkerContext,
    ApiWorkerContext,
    UiWorkerContext,
    WorkerExecutionContext,
)
from testing_agent.models.worker_task import WorkerTask
from testing_agent.schemas.workers import (
    WorkerClaimRequest,
    WorkerTaskEventRequest,
)

LEASE_SECONDS = 30


def final_run_status(status: str | None) -> str:
    if status is None or status in {"", "completed", "passed", "success"}:
        return "success"
    if status in {"failed", "failure"}:
        return "failed"
    return status


def task_payload(task: WorkerTask, context: WorkerExecutionContext | None) -> dict[str, Any]:
    return {
        "taskId": task.task_id,
        "taskType": task.task_type,
        "domain": task.domain,
        "runId": task.run_id,
        "suiteId": context.suite_id if isinstance(context, UiWorkerContext) else None,
        "caseId": context.case_id
        if isinstance(context, (ApiWorkerContext, UiWorkerContext))
        else None,
        "collectionRunId": context.collection_run_id
        if isinstance(context, ApiWorkerContext)
        else None,
        "collectionId": context.collection_id if isinstance(context, ApiWorkerContext) else None,
        "generateTaskId": context.generate_task_id
        if isinstance(context, AiWorkerContext)
        else None,
        "status": task.status,
    }


def json_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def parse_event_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def update_task_claimed(task: WorkerTask, body: WorkerClaimRequest) -> None:
    now = datetime.now(UTC)
    task.worker_id = body.worker_id
    task.status = RunStatus.CLAIMED.value
    task.heartbeat_at = now
    task.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)


async def apply_event_to_task(
    task: WorkerTask, body: WorkerTaskEventRequest, status: str | None
) -> None:
    now = datetime.now(UTC)
    task.worker_id = body.worker_id
    if status:
        task.status = status
    task.heartbeat_at = now
    task.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    if body.started_at:
        task.started_at = parse_event_time(body.started_at)
    if body.finished_at or status in {"success", "failed", "error", "completed"}:
        task.finished_at = parse_event_time(body.finished_at) or now
    if body.error_message is not None:
        task.error_message = body.error_message
