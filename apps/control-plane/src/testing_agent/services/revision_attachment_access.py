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
        "api_case_generate",
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
    from testing_agent.services.stage_storage.worker_service import DirectStageWorkerService

    session = getattr(service.repository, "session", None)
    from testing_agent.services.standalone_worker_service import StandaloneWorkerService

    standalone = StandaloneWorkerService(session) if session is not None else None
    if standalone is not None and await standalone.is_standalone(task):
        authority = await standalone.authorize(task)
        snapshot = authority.dispatched_attempt.input_snapshot_json or {}
        config = snapshot.get("config") or {}
        attachments = config.get("revisionAttachments") if isinstance(config, dict) else None
        if not isinstance(attachments, list) or not any(
            isinstance(item, dict) and item.get("fileId") == file_id for item in attachments
        ):
            raise ErrNotFound()
        image = await files.get(file_id)
        if (
            image.project_id != authority.task.project_id
            or image.resource_type != REVISION_ATTACHMENT_RESOURCE_TYPE
            or image.resource_id != authority.execution.execution_id
            or image.purpose != "attachment"
            or image.status != "attached"
            or image.content_type not in REVISION_IMAGE_CONTENT_TYPES
        ):
            raise ErrNotFound()
        return await files.ticket(image)
    direct = DirectStageWorkerService(session) if session is not None else None
    if direct is not None and await direct.is_direct(task):
        authority = await direct.authorize(task)
        config = authority.input_snapshot.get("config") or {}
        attachments = config.get("revisionAttachments") if isinstance(config, dict) else None
        if not isinstance(attachments, list) or not any(
            isinstance(item, dict) and item.get("fileId") == file_id for item in attachments
        ):
            raise ErrNotFound()
        image = await files.get(file_id)
        if (
            image.project_id != authority.task.project_id
            or image.resource_type != REVISION_ATTACHMENT_RESOURCE_TYPE
            or image.resource_id != authority.attempt_id
            or image.purpose != "attachment"
            or image.status != "attached"
            or image.content_type not in REVISION_IMAGE_CONTENT_TYPES
        ):
            raise ErrNotFound()
        return await files.ticket(image)
    raise ErrNotFound()
