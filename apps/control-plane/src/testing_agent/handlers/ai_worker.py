from __future__ import annotations

from fastapi import Depends
from fastapi.responses import JSONResponse, Response

from testing_agent.api.deps import get_file_service, get_worker_task_service
from testing_agent.schemas.workers import (
    WorkerClaimRequest,
    WorkerProgressRequest,
    WorkerTaskEventRequest,
)
from testing_agent.services.worker_task import WorkerTaskService


async def claim_task(
    body: WorkerClaimRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    payload = await service.claim("ai", body)
    if payload is None:
        return Response(status_code=204)
    return payload


async def get_snapshot(
    task_id: str,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    return await service.snapshot("ai", task_id)


async def mark_started(
    task_id: str,
    body: WorkerTaskEventRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    await service.started("ai", task_id, body)
    return Response(status_code=204)


async def heartbeat(
    task_id: str,
    body: WorkerTaskEventRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    await service.heartbeat("ai", task_id, body)
    return Response(status_code=204)


async def complete_task(
    task_id: str,
    body: WorkerTaskEventRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    await service.complete("ai", task_id, body)
    return Response(status_code=204)


async def list_project_skills(
    project_id: str,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    return await service.list_project_skills(project_id)


async def llm_credentials(
    task_id: str,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    return await service.llm_credentials(task_id)


async def gitlab_credentials(
    task_id: str,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    return await service.gitlab_credentials(task_id)


async def requirement_document(
    task_id: str,
    service: WorkerTaskService = Depends(get_worker_task_service),
    files=Depends(get_file_service),
):
    requirement = await service.requirement_document(task_id)
    row = await files.get(requirement.document_file_id)
    ticket = await files.ticket(row)
    return JSONResponse(ticket, headers={"Cache-Control": "no-store"})


async def source_archive(
    task_id: str,
    service: WorkerTaskService = Depends(get_worker_task_service),
    files=Depends(get_file_service),
):
    file_id = await service.source_archive(task_id)
    row = await files.get(file_id)
    ticket = await files.ticket(row)
    return JSONResponse(ticket, headers={"Cache-Control": "no-store"})


async def report_progress(
    task_id: str,
    body: WorkerProgressRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    await service.progress(task_id, body)
    return Response(status_code=204)
