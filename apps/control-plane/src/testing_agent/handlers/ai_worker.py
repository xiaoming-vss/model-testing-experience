from __future__ import annotations

from fastapi import Depends, Query
from fastapi.responses import JSONResponse, Response

from testing_agent.api.deps import get_file_service, get_worker_task_service
from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.schemas.workers import (
    AiWorkerClaimPayload,
    AiWorkerProgressRequest,
    AiWorkerTaskEventRequest,
    WorkerClaimRequest,
    WorkerProgressRequest,
    WorkerTaskEventRequest,
)
from testing_agent.services.worker_task import WorkerTaskService


def _event_body(body: AiWorkerTaskEventRequest) -> WorkerTaskEventRequest:
    data = body.model_dump()
    data["run_id"] = data.pop("attempt_id")
    return WorkerTaskEventRequest(**data)


def _progress_body(body: AiWorkerProgressRequest) -> WorkerProgressRequest:
    data = body.model_dump()
    data["run_id"] = data.pop("attempt_id")
    return WorkerProgressRequest(**data)


async def claim_task(
    body: WorkerClaimRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    payload = await service.claim("ai", body)
    if payload is None:
        return Response(status_code=204)
    data = dict(payload)
    attempt_id = data.get("attemptId")
    if not isinstance(attempt_id, str) or not attempt_id.strip():
        raise dynamic_error(
            ErrBadRequest,
            "AI 任务缺少 attemptId，请确认控制面与 Worker 版本一致",
        )
    data["attempt_id"] = attempt_id
    return AiWorkerClaimPayload(**data)


async def get_snapshot(
    task_id: str,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    return await service.snapshot("ai", task_id)


async def mark_started(
    task_id: str,
    body: AiWorkerTaskEventRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    await service.started("ai", task_id, _event_body(body))
    return Response(status_code=204)


async def heartbeat(
    task_id: str,
    body: AiWorkerTaskEventRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    await service.heartbeat("ai", task_id, _event_body(body))
    return Response(status_code=204)


async def complete_task(
    task_id: str,
    body: AiWorkerTaskEventRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    await service.complete("ai", task_id, _event_body(body))
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


async def report_progress(
    task_id: str,
    body: AiWorkerProgressRequest,
    service: WorkerTaskService = Depends(get_worker_task_service),
):
    await service.progress(task_id, _progress_body(body))
    return Response(status_code=204)


async def requirement_image(
    task_id: str,
    file_id: str,
    worker_id: str = Query(alias="workerId"),
    service: WorkerTaskService = Depends(get_worker_task_service),
    files=Depends(get_file_service),
) -> JSONResponse:
    from testing_agent.services.requirement_image import requirement_image_ticket

    ticket = await requirement_image_ticket(task_id, file_id, worker_id, service, files)
    return JSONResponse(ticket, headers={"Cache-Control": "no-store"})


async def revision_attachment(
    task_id: str,
    file_id: str,
    worker_id: str = Query(alias="workerId"),
    service: WorkerTaskService = Depends(get_worker_task_service),
    files=Depends(get_file_service),
) -> JSONResponse:
    from testing_agent.services.revision_attachment_access import revision_attachment_ticket

    ticket = await revision_attachment_ticket(task_id, file_id, worker_id, service, files)
    return JSONResponse(ticket, headers={"Cache-Control": "no-store"})
