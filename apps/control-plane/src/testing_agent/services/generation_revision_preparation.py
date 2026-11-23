"""Verify revision uploads outside locks and recheck them before attachment."""

# transaction-bound: attachment metadata and the worker attempt share one commit.

import asyncio
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.generation_root_fingerprints import IncompleteRootInput
from testing_agent.models.stored_file import StoredFile
from testing_agent.services.generation_document_preparation import (
    PreparedFile,
    project_prepared_file,
    read_verified_object,
)
from testing_agent.services.revision_attachments import (
    MAX_REVISION_IMAGE_BYTES,
    REVISION_IMAGE_CONTENT_TYPES,
    attach_revision_attachments,
    normalize_attachment_file_ids,
)
from testing_agent.services.stored_file import StoredFileService, utcnow


@dataclass(frozen=True)
class PreparedRevisionUploads:
    actor_id: str
    project_id: str
    files: tuple[PreparedFile, ...]


def _eligible(row: StoredFile, *, actor_id: str, project_id: str) -> bool:
    return bool(
        actor_id
        and project_id
        and row.project_id == project_id
        and row.uploaded_by == actor_id
        and row.purpose == "attachment"
        and row.status == "ready"
        and row.expires_at > utcnow()
        and row.content_type in REVISION_IMAGE_CONTENT_TYPES
        and 0 < row.size <= MAX_REVISION_IMAGE_BYTES
    )


async def prepare_revision_uploads(
    session: AsyncSession,
    *,
    files: StoredFileService,
    project_id: str,
    actor_id: str,
    file_ids: list[str],
) -> PreparedRevisionUploads:
    """Read completed objects without locks; the caller must authorize first.

    Roll back the read transaction before acquiring business locks. Object
    errors propagate and never count as a verified image.
    """
    if not actor_id or not project_id or files.session is not session:
        raise IncompleteRootInput("revision upload scope is unavailable")
    ids = normalize_attachment_file_ids(file_ids)
    rows = list(
        (await session.scalars(select(StoredFile).where(StoredFile.file_id.in_(ids)))).all()
    )
    by_id = {row.file_id: row for row in rows}
    if set(by_id) != set(ids):
        raise IncompleteRootInput("revision upload is unavailable")
    prepared = []
    for file_id in ids:
        row = by_id[file_id]
        if not _eligible(row, actor_id=actor_id, project_id=project_id):
            raise IncompleteRootInput("revision upload is unavailable")
        prepared.append(
            project_prepared_file(row, purpose="attachment", bucket=files.settings.bucket)
        )
    for item in prepared:
        await asyncio.to_thread(read_verified_object, files.storage, item, keep_content=False)
    return PreparedRevisionUploads(actor_id, project_id, tuple(prepared))


async def attach_prepared_revision_uploads(
    session: AsyncSession,
    *,
    files: StoredFileService,
    prepared: PreparedRevisionUploads,
    actor_id: str,
    project_id: str,
    attempt_id: str,
) -> tuple[tuple[dict[str, str], ...], dict[str, str]]:
    """Recheck exact file identities and attach them within the caller transaction."""
    if (
        not attempt_id
        or prepared.actor_id != actor_id
        or prepared.project_id != project_id
        or files.session is not session
    ):
        raise IncompleteRootInput("revision upload scope changed")
    ids = tuple(item.file_id for item in prepared.files)
    if len(ids) != len(set(ids)):
        raise IncompleteRootInput("revision upload identity is duplicated")
    rows = list(
        (
            await session.scalars(
                select(StoredFile)
                .where(StoredFile.file_id.in_(ids))
                .order_by(StoredFile.file_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    by_id = {row.file_id: row for row in rows}
    if set(by_id) != set(ids):
        raise IncompleteRootInput("revision upload changed")
    for item in prepared.files:
        row = by_id[item.file_id]
        if not _eligible(row, actor_id=actor_id, project_id=project_id) or (
            project_prepared_file(row, purpose="attachment", bucket=files.settings.bucket) != item
        ):
            raise IncompleteRootInput("revision upload changed")
    attachments = await attach_revision_attachments(
        files, user_id=actor_id, project_id=project_id, run_id=attempt_id, file_ids=list(ids)
    )
    return attachments, {item.file_id: item.sha256 for item in prepared.files}
