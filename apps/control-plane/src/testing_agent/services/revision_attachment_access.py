"""Authorize an image attached to the active AI run for its worker."""

from datetime import UTC, datetime

from testing_agent.core.errors import ErrForbidden, ErrNotFound
from testing_agent.services.revision_attachments import (
    REVISION_ATTACHMENT_RESOURCE_TYPE,
    REVISION_IMAGE_CONTENT_TYPES,
)
from testing_agent.services.stored_file import StoredFileService
from testing_agent.services.worker_task import WorkerTaskService


async def revision_attachment_ticket(
    task_id: str,
    file_id: str,
    worker_id: str,
    service: WorkerTaskService,
    files: StoredFileService,
) -> dict:
    """Return a fresh download ticket for a revision image owned by this run."""
    task = await service.repository.get_worker_task("ai", task_id)
    if task is None or task.task_type not in {
        "requirement_analysis",
        "functional_case_generate",
    }:
        raise ErrNotFound()
    lease = task.lease_expires_at
    if (
        task.worker_id != worker_id
        or task.status not in {"claimed", "running"}
        or lease is None
        or lease.replace(tzinfo=UTC) <= datetime.now(UTC)
    ):
        raise ErrForbidden()
    run = await service.repository.get_ai_run(task.run_id)
    if run is None:
        raise ErrNotFound()
    image = await files.get(file_id)
    if (
        image.project_id != run.project_id
        or image.resource_type != REVISION_ATTACHMENT_RESOURCE_TYPE
        or image.resource_id != run.run_id
        or image.purpose != "attachment"
        or image.status != "attached"
        or image.content_type not in REVISION_IMAGE_CONTENT_TYPES
    ):
        raise ErrNotFound()
    return await files.ticket(image)
