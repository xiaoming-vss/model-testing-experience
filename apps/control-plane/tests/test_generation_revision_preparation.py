"""Revision uploads must remain the verified files until attachment."""

from datetime import timedelta
from hashlib import sha256
from types import SimpleNamespace

import pytest
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.memory_storage import Storage

from testing_agent.core.utc import naive_utcnow
from testing_agent.domain.generation_root_fingerprints import IncompleteRootInput
from testing_agent.models.stored_file import StoredFile
from testing_agent.services.generation_revision_preparation import (
    attach_prepared_revision_uploads,
    prepare_revision_uploads,
)
from testing_agent.services.stored_file import StoredFileService


async def test_revision_uploads_verify_bytes_and_recheck_before_attach(db):  # noqa: F811
    storage = Storage(b"image content", key="sealed")
    row = StoredFile(
        file_id="image",
        project_id="p",
        uploaded_by="u",
        filename="screen.png",
        content_type="image/png",
        size=len(storage.data),
        sha256=sha256(storage.data).hexdigest(),
        bucket="bucket",
        object_key="sealed",
        staging_key="",
        status="ready",
        purpose="attachment",
        resource_type="",
        resource_id="",
        expires_at=naive_utcnow() + timedelta(hours=1),
    )
    db.add(row)
    db.commit()
    session = AsyncSessionAdapter(db)
    files = StoredFileService(session, SimpleNamespace(bucket="bucket", enabled=True), storage)
    options = dict(files=files, project_id="p", actor_id="u")
    prepared = await prepare_revision_uploads(session, **options, file_ids=["image"])
    with pytest.raises(IncompleteRootInput):
        await prepare_revision_uploads(
            session, files=files, project_id="p", actor_id="another", file_ids=["image"]
        )

    storage.data = b"changed image"
    with pytest.raises(IncompleteRootInput):
        await prepare_revision_uploads(session, **options, file_ids=["image"])
    storage.data = b"image content"
    row.filename = "changed.png"
    db.flush()
    with pytest.raises(IncompleteRootInput, match="changed"):
        await attach_prepared_revision_uploads(
            session, **options, prepared=prepared, attempt_id="attempt"
        )
    db.rollback()
    attachments, hashes = await attach_prepared_revision_uploads(
        session, **options, prepared=prepared, attempt_id="attempt"
    )
    assert attachments == (
        {"fileId": "image", "filename": "screen.png", "contentType": "image/png"},
    )
    assert hashes == {"image": sha256(storage.data).hexdigest()}
    assert row.status == "attached" and row.resource_id == "attempt"
    db.rollback()
    assert row.status == "ready"
