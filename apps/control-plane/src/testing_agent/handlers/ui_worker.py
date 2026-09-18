from __future__ import annotations

from fastapi import Depends, Response

from testing_agent.api.deps import get_worker_task_service
from testing_agent.schemas.workers import WorkerClaimRequest, WorkerTaskEventRequest
from testing_agent.services.worker_task import WorkerTaskService


async def claim_task(
    body: WorkerClaimRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    payload = await service.claim("ui", body)
    if payload is None:
        return Response(status_code=204)
    return payload


async def get_snapshot(
    task_id: str,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    return await service.snapshot("ui", task_id)


async def mark_started(
    task_id: str,
    body: WorkerTaskEventRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    await service.started("ui", task_id, body)
    return Response(status_code=204)


async def heartbeat(
    task_id: str,
    body: WorkerTaskEventRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    await service.heartbeat("ui", task_id, body)
    return Response(status_code=204)


async def complete_task(
    task_id: str,
    body: WorkerTaskEventRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    await service.complete("ui", task_id, body)
    return Response(status_code=204)


async def mark_suite_item_started(
    task_id: str,
    item_id: str,
    body: WorkerTaskEventRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    await service.start_ui_suite_item(task_id, item_id, body)
    return Response(status_code=204)


async def complete_suite_item(
    task_id: str,
    item_id: str,
    body: WorkerTaskEventRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    await service.complete_ui_suite_item(task_id, item_id, body)
    return Response(status_code=204)
