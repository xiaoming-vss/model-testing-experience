"""Prepare requirement source files before acquiring business row locks."""

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.generation_root_fingerprints import IncompleteRootInput
from testing_agent.domain.generation_source_closure import RootSnapshot
from testing_agent.domain.rich_text import extract_file_ids
from testing_agent.models.requirement import Requirement
from testing_agent.models.stored_file import StoredFile
from testing_agent.repositories.generation_root_inputs import (
    lock_requirement_document_root,
    read_requirement_document_identity,
    read_requirement_file_metadata,
)
from testing_agent.services.stored_file import StoredFileService

# transaction-bound: the final file identity recheck shares the root row locks.


@dataclass(frozen=True)
class PreparedFile:
    file_id: str
    project_id: str
    purpose: str
    filename: str
    content_type: str
    bucket: str
    object_key: str
    size: int
    sha256: str


@dataclass(frozen=True)
class PreparedRequirementDocument:
    requirement_id: str
    document_type: str
    document: PreparedFile
    attachments: tuple[PreparedFile, ...]


def project_prepared_file(row: StoredFile, *, purpose: str, bucket: str) -> PreparedFile:
    if (
        row.purpose != purpose
        or row.bucket != bucket
        or not row.object_key
        or not row.sha256
        or row.size < 0
    ):
        raise IncompleteRootInput("requirement file metadata is incomplete")
    return PreparedFile(
        row.file_id,
        row.project_id,
        row.purpose,
        row.filename,
        row.content_type,
        row.bucket,
        row.object_key,
        row.size,
        row.sha256,
    )


def read_verified_object(storage: Any, file: PreparedFile, *, keep_content: bool) -> bytes:
    """Read the sealed object in a worker thread with a hard metadata size bound."""
    result = storage.get_object(file.object_key)
    body = result["Body"]
    digest, count = sha256(), 0
    content: list[bytes] = []
    try:
        for chunk in body.iter_chunks(1024 * 1024):
            count += len(chunk)
            if count > file.size:
                raise IncompleteRootInput("requirement object size changed")
            digest.update(chunk)
            if keep_content:
                content.append(chunk)
    finally:
        body.close()
    if count != file.size or digest.hexdigest() != file.sha256:
        raise IncompleteRootInput("requirement object checksum changed")
    return b"".join(content)


async def prepare_requirement_document(
    session: AsyncSession, *, requirement_id: str, files: StoredFileService
) -> PreparedRequirementDocument:
    """Read actual objects without holding row locks; caller must authorize first.

    The caller must start preparation before taking any business row locks and
    recheck the returned identities with ``lock_prepared_requirement_root`` in
    the subsequent transaction. A storage exception is not converted to success.
    """
    file_id, document_type, document_hash = await read_requirement_document_identity(
        session, requirement_id=requirement_id
    )
    rows = await read_requirement_file_metadata(
        session, requirement_id=requirement_id, file_ids=(file_id,)
    )
    document = project_prepared_file(rows[0], purpose="requirement", bucket=files.settings.bucket)
    if document.sha256 != document_hash:
        raise IncompleteRootInput("requirement document metadata is inconsistent")
    richtext = document_type == "richtext"
    if richtext and document.size > 1024 * 1024:
        raise IncompleteRootInput("rich text document exceeds its size limit")
    data = await asyncio.to_thread(
        read_verified_object, files.storage, document, keep_content=richtext
    )
    attachment_ids: tuple[str, ...] = ()
    if richtext:
        try:
            html = data.decode("utf-8")
            if "\x00" in html:
                raise ValueError("NUL in document")
            attachment_ids = tuple(extract_file_ids(html))
        except (UnicodeDecodeError, ValueError) as exc:
            raise IncompleteRootInput("requirement rich text is invalid") from exc
    attachments: tuple[PreparedFile, ...] = ()
    if attachment_ids:
        image_rows = await read_requirement_file_metadata(
            session, requirement_id=requirement_id, file_ids=attachment_ids
        )
        by_id = {row.file_id: row for row in image_rows}
        if any(
            by_id[item].content_type not in {"image/png", "image/jpeg"} for item in attachment_ids
        ):
            raise IncompleteRootInput("requirement attachment type is invalid")
        attachments = tuple(
            project_prepared_file(by_id[item], purpose="attachment", bucket=files.settings.bucket)
            for item in attachment_ids
        )
        for attachment in attachments:
            await asyncio.to_thread(
                read_verified_object, files.storage, attachment, keep_content=False
            )
    return PreparedRequirementDocument(requirement_id, document_type, document, attachments)


async def lock_prepared_requirement_root(
    session: AsyncSession, *, prepared: PreparedRequirementDocument
) -> RootSnapshot:
    """Recheck prepared object identities under the final caller-owned locks."""
    root = await lock_requirement_document_root(
        session,
        requirement_id=prepared.requirement_id,
        referenced_attachment_ids=tuple(item.file_id for item in prepared.attachments)
        if prepared.document_type == "richtext"
        else None,
    )
    current_requirement = await session.scalar(
        select(Requirement)
        .where(Requirement.requirement_id == prepared.requirement_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        current_requirement is None
        or current_requirement.document_file_id != prepared.document.file_id
        or current_requirement.document_type != prepared.document_type
        or current_requirement.document_hash != prepared.document.sha256
    ):
        raise IncompleteRootInput("requirement document changed during preparation")
    expected = (prepared.document, *prepared.attachments)
    rows = (
        await session.scalars(
            select(StoredFile)
            .where(StoredFile.file_id.in_(tuple(item.file_id for item in expected)))
            .order_by(StoredFile.file_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    current = {row.file_id: row for row in rows}
    if set(current) != {item.file_id for item in expected}:
        raise IncompleteRootInput("requirement file changed during preparation")
    for item in expected:
        if (
            project_prepared_file(current[item.file_id], purpose=item.purpose, bucket=item.bucket)
            != item
        ):
            raise IncompleteRootInput("requirement file changed during preparation")
    return root


def bind_prepared_document_source(
    *, source: dict[str, Any], prepared: PreparedRequirementDocument, root: RootSnapshot
) -> dict[str, Any]:
    """Bind the verified file and image identities to the actual Worker source."""
    from testing_agent.domain.generation_root_fingerprints import fingerprint_root_input

    source = deepcopy(source)
    expected = {
        "requirementId": prepared.requirement_id,
        "documentFileId": prepared.document.file_id,
        "documentType": prepared.document_type,
        "documentFilename": prepared.document.filename,
        "documentHash": prepared.document.sha256,
    }
    if any(source.get(key) != value for key, value in expected.items()):
        raise IncompleteRootInput("worker source does not match the prepared document")
    if prepared.document_type == "richtext":
        source["attachmentHashes"] = [
            {"fileId": item.file_id, "sha256": item.sha256} for item in prepared.attachments
        ]
    if fingerprint_root_input("requirement_document", source) != root:
        raise IncompleteRootInput("worker source does not match the locked document root")
    return source
