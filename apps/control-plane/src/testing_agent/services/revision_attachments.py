"""Validate and attach images supplied with an AI stage revision request."""

from __future__ import annotations

from typing import Any

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.services.stored_file import StoredFileService

MAX_REVISION_ATTACHMENTS = 6

MAX_REVISION_IMAGE_BYTES = 10 * 1024 * 1024

REVISION_IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg"}

REVISION_ATTACHMENT_RESOURCE_TYPE = "ai_generate_run"

_INVALID = "继续优化图片无效或已过期，请重新上传"


def normalize_attachment_file_ids(value: Any) -> list[str]:
    """Return unique file ids, rejecting client-supplied shapes we cannot authorize."""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_REVISION_ATTACHMENTS:
        raise dynamic_error(ErrBadRequest, f"继续优化最多附加 {MAX_REVISION_ATTACHMENTS} 张图片")
    file_ids: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or item in file_ids:
            raise dynamic_error(ErrBadRequest, _INVALID)
        file_ids.append(item)
    return file_ids


async def attach_revision_attachments(
    files: StoredFileService,
    *,
    user_id: str,
    project_id: str,
    run_id: str,
    file_ids: list[str],
) -> tuple[dict[str, str], ...]:
    """Attach uploaded screenshots to the run and freeze their metadata for the attempt.

    The uploader and project must match the revision actor. ``attach`` performs the
    expiry/purpose checks and keeps this inside the caller's transaction.
    """
    attachments: list[dict[str, str]] = []
    for file_id in file_ids:
        row = await files.get(file_id)
        if (
            row.project_id != project_id
            or row.uploaded_by != user_id
            or row.purpose != "attachment"
            or row.content_type not in REVISION_IMAGE_CONTENT_TYPES
            or row.size > MAX_REVISION_IMAGE_BYTES
        ):
            raise dynamic_error(ErrBadRequest, _INVALID)
        await files.attach(
            user_id,
            file_id,
            project_id,
            REVISION_ATTACHMENT_RESOURCE_TYPE,
            run_id,
            purpose="attachment",
        )
        attachments.append(
            {
                "fileId": row.file_id,
                "filename": row.filename,
                "contentType": row.content_type,
            }
        )
    return tuple(attachments)
