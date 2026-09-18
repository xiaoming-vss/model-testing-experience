from __future__ import annotations

from pathlib import Path

from fastapi import Depends, Response
from fastapi.responses import FileResponse

from testing_agent.api.deps import get_worker_task_service
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
):
    requirement = await service.requirement_document(task_id)
    path = Path(requirement.document_storage_path)
    if path.exists() and path.is_file():
        return FileResponse(
            path,
            filename=requirement.document_filename or "requirement",
            media_type="application/octet-stream",
        )
    content = getattr(requirement, "content", None)
    return Response(
        content=content if content is not None else requirement.document_content.encode("utf-8"),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{requirement.document_filename or "requirement"}"'
            )
        },
    )


async def source_archive(
    task_id: str,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    archive = await service.source_archive(task_id)
    return FileResponse(
        archive.storage_path,
        filename=archive.filename,
        media_type="application/zip",
    )


async def report_progress(
    task_id: str,
    body: WorkerProgressRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    await service.progress(task_id, body)
    return Response(status_code=204)
