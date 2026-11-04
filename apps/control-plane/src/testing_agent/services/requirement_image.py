"""Authorize a referenced image against the active requirement-analysis run."""

import asyncio
from datetime import UTC, datetime

from testing_agent.core.errors import ErrForbidden, ErrNotFound
from testing_agent.domain.rich_text import extract_file_ids
from testing_agent.services.stored_file import StoredFileService
from testing_agent.services.worker_task import WorkerTaskService


async def requirement_image_ticket(
    task_id: str,
    file_id: str,
    worker_id: str,
    service: WorkerTaskService,
    files: StoredFileService,
) -> dict:
    # Reuses current execution authority and immutable source identity checks.
    requirement = await service.requirement_document(task_id)
    task = await service.repository.get_worker_task("ai", task_id)
    if task is None or task.task_type != "requirement_analysis":
        raise ErrNotFound()
    lease = task.lease_expires_at
    if (
        task.worker_id != worker_id
        or task.status not in {"claimed", "running"}
        or lease is None
        or lease.replace(tzinfo=UTC) <= datetime.now(UTC)
    ):
        raise ErrForbidden()
    if requirement.document_type != "richtext":
        raise ErrNotFound()
    from testing_agent.services.stage_storage.worker_service import DirectStageWorkerService

    session = getattr(service.repository, "session", None)
    direct = DirectStageWorkerService(session) if session is not None else None
    if direct is not None and await direct.is_direct(task):
        authority = await direct.authorize(task)
        project_id = authority.task.project_id
    else:
        raise ErrNotFound()
    document = await files.get(requirement.document_file_id)
    image = await files.get(file_id)
    for row, purpose in ((document, "requirement"), (image, "attachment")):
        if (
            row.project_id != project_id
            or row.resource_type != "requirement"
            or row.resource_id != requirement.requirement_id
            or row.purpose != purpose
            or row.status != "attached"
        ):
            raise ErrNotFound()
    if image.content_type not in {"image/png", "image/jpeg"}:
        raise ErrNotFound()
    html = await asyncio.to_thread(files.storage.read_text, document.object_key)
    if file_id not in extract_file_ids(html):
        raise ErrNotFound()
    return await files.ticket(image)
