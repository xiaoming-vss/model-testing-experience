from __future__ import annotations

from fastapi import Depends, Response

from testing_agent.api.deps import get_worker_task_service
from testing_agent.core.errors import success_payload
from testing_agent.schemas.workers import WorkerClaimRequest, WorkerTaskEventRequest
from testing_agent.services.worker_task import WorkerTaskService


async def claim_task(
    body: WorkerClaimRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    payload = await service.claim("api", body)
    if payload is None:
        return Response(status_code=204)
    return success_payload(payload)


async def get_snapshot(
    task_id: str,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    return success_payload(await service.snapshot("api", task_id))


async def mark_started(
    task_id: str,
    body: WorkerTaskEventRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    return success_payload(await service.started("api", task_id, body))


async def heartbeat(
    task_id: str,
    body: WorkerTaskEventRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    return success_payload(await service.heartbeat("api", task_id, body))


async def complete_task(
    task_id: str,
    body: WorkerTaskEventRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    return success_payload(await service.complete("api", task_id, body))


async def mark_collection_item_started(
    task_id: str,
    item_id: str,
    body: WorkerTaskEventRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    return success_payload(await service.start_api_collection_item(task_id, item_id, body))


async def complete_collection_item(
    task_id: str,
    item_id: str,
    body: WorkerTaskEventRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    return success_payload(await service.complete_api_collection_item(task_id, item_id, body))
