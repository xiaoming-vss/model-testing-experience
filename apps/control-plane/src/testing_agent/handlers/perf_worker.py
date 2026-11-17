from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Query, Response
from fastapi.responses import StreamingResponse

from testing_agent.api.deps import get_perf_worker_service
from testing_agent.core.object_storage import download_disposition
from testing_agent.schemas.perf_worker import (
    PerfHeartbeatRequest,
    PerfResultEvent,
    PerfStartedRequest,
)
from testing_agent.schemas.workers import WorkerClaimRequest


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


async def claim(
    body: WorkerClaimRequest,
    service=Depends(get_perf_worker_service),
):
    payload = await service.claim(body.worker_id)
    if payload is None:
        return Response(status_code=204, headers={"Cache-Control": "no-store"})
    return payload


async def snapshot(
    task_id: str,
    worker_id: Annotated[str, Query(alias="workerId", min_length=1, max_length=120)],
    service=Depends(get_perf_worker_service),
):
    return await service.snapshot(task_id, worker_id)


async def started(
    task_id: str,
    body: PerfStartedRequest,
    service=Depends(get_perf_worker_service),
):
    await service.started(task_id, body.worker_id, body.started_at)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


async def heartbeat(
    task_id: str,
    body: PerfHeartbeatRequest,
    service=Depends(get_perf_worker_service),
):
    return await service.heartbeat(task_id, body.worker_id)


async def control(
    task_id: str,
    worker_id: Annotated[str, Query(alias="workerId", min_length=1, max_length=120)],
    service=Depends(get_perf_worker_service),
):
    return await service.control(task_id, worker_id)


async def completed(
    task_id: str,
    body: PerfResultEvent,
    service=Depends(get_perf_worker_service),
):
    return await service.complete(task_id, body)


async def data_file(
    task_id: str,
    file_id: str,
    worker_id: Annotated[str, Query(alias="workerId", min_length=1, max_length=120)],
    service=Depends(get_perf_worker_service),
):
    row, body = await service.data_file(task_id, file_id, worker_id)
    return StreamingResponse(
        _iter_body(body),
        media_type=row.content_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Length": str(row.size),
            "Content-Disposition": download_disposition(row.filename),
            "X-Content-SHA256": row.sha256,
        },
    )


def _iter_body(body) -> Iterator[bytes]:
    try:
        yield from body.iter_chunks(1024 * 1024)
    finally:
        body.close()
