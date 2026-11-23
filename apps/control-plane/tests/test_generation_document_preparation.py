"""Actual requirement objects are checked before final locked source validation."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace

import pytest
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401

from testing_agent.domain.generation_root_fingerprints import IncompleteRootInput
from testing_agent.models.requirement import Requirement
from testing_agent.models.stored_file import StoredFile
from testing_agent.services.generation_document_preparation import (
    bind_prepared_document_source,
    lock_prepared_requirement_root,
    prepare_requirement_document,
)


class Body:
    def __init__(self, data):
        self.data = data
        self.closed = False

    def iter_chunks(self, chunk_size):
        yield self.data[:chunk_size]
        if len(self.data) > chunk_size:
            yield self.data[chunk_size:]

    def close(self):
        self.closed = True


class Storage:
    def __init__(self, objects):
        self.objects = objects
        self.opened = []

    def get_object(self, key):
        body = Body(self.objects[key])
        self.opened.append((key, body))
        return {"Body": body}


def seed(sync, file_id, data, *, purpose, filename, resource_id="req"):
    sync.add(
        StoredFile(
            file_id=file_id,
            project_id="p",
            uploaded_by="u",
            filename=filename,
            content_type="text/html" if purpose == "requirement" else "image/png",
            size=len(data),
            sha256=sha256(data).hexdigest(),
            bucket="bucket",
            object_key=file_id,
            staging_key="",
            status="attached",
            purpose=purpose,
            resource_type="requirement",
            resource_id=resource_id,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )


def prepare_fixture(sync):
    html = b'<p>Requirement</p><img data-file-id="image">'
    image = b"example image"
    requirement = sync.query(Requirement).filter_by(requirement_id="req").one()
    requirement.document_type = "richtext"
    requirement.document_file_id = "document"
    requirement.document_filename = "requirement.html"
    requirement.document_hash = sha256(html).hexdigest()
    seed(sync, "document", html, purpose="requirement", filename="requirement.html")
    seed(sync, "image", image, purpose="attachment", filename="image.png")
    seed(sync, "unused", b"unused", purpose="attachment", filename="unused.png")
    sync.commit()
    storage = Storage({"document": html, "image": image})
    return SimpleNamespace(settings=SimpleNamespace(bucket="bucket"), storage=storage)


async def test_reads_real_document_and_only_referenced_images(database):  # noqa: F811
    sync, _, _ = database
    files = prepare_fixture(sync)
    session = AsyncSessionAdapter(sync)
    prepared = await prepare_requirement_document(session, requirement_id="req", files=files)
    assert [item.file_id for item in prepared.attachments] == ["image"]
    assert [key for key, _ in files.storage.opened] == ["document", "image"]
    assert all(body.closed for _, body in files.storage.opened)
    sync.commit()
    root = await lock_prepared_requirement_root(session, prepared=prepared)
    assert root.resource_kind == "requirement_document" and root.resource_id == "req"
    source = {
        "requirementId": "req",
        "documentFileId": "document",
        "documentType": "richtext",
        "documentFilename": "requirement.html",
        "documentHash": prepared.document.sha256,
    }
    bound = bind_prepared_document_source(source=source, prepared=prepared, root=root)
    assert bound["attachmentHashes"] == [
        {"fileId": "image", "sha256": prepared.attachments[0].sha256}
    ]
    assert "attachmentHashes" not in source
    with pytest.raises(IncompleteRootInput, match="does not match"):
        bind_prepared_document_source(
            source={**source, "documentFileId": "other"}, prepared=prepared, root=root
        )


async def test_tampered_or_missing_objects_are_not_accepted(database):  # noqa: F811
    sync, _, _ = database
    files = prepare_fixture(sync)
    session = AsyncSessionAdapter(sync)
    files.storage.objects["image"] = b"bad"
    with pytest.raises(IncompleteRootInput, match="checksum|size"):
        await prepare_requirement_document(session, requirement_id="req", files=files)
    assert all(body.closed for _, body in files.storage.opened)
    del files.storage.objects["image"]
    with pytest.raises(KeyError):
        await prepare_requirement_document(session, requirement_id="req", files=files)


async def test_changes_between_preparation_and_lock_are_rejected(database):  # noqa: F811
    sync, _, _ = database
    files = prepare_fixture(sync)
    session = AsyncSessionAdapter(sync)
    prepared = await prepare_requirement_document(session, requirement_id="req", files=files)
    sync.commit()
    image = sync.query(StoredFile).filter_by(file_id="image").one()
    image.object_key = "replaced-object"
    sync.commit()
    with pytest.raises(IncompleteRootInput, match="changed during preparation"):
        await lock_prepared_requirement_root(session, prepared=prepared)


async def test_image_content_type_change_is_rejected_after_preparation(database):  # noqa: F811
    sync, _, _ = database
    files = prepare_fixture(sync)
    session = AsyncSessionAdapter(sync)
    prepared = await prepare_requirement_document(session, requirement_id="req", files=files)
    sync.commit()
    sync.query(StoredFile).filter_by(file_id="image").one().content_type = "text/plain"
    sync.commit()
    with pytest.raises(IncompleteRootInput, match="changed during preparation"):
        await lock_prepared_requirement_root(session, prepared=prepared)


async def test_richtext_cannot_reference_another_requirements_image(database):  # noqa: F811
    sync, _, _ = database
    files = prepare_fixture(sync)
    image = sync.query(StoredFile).filter_by(file_id="image").one()
    image.resource_id = "other"
    sync.commit()
    with pytest.raises(IncompleteRootInput, match="out of scope"):
        await prepare_requirement_document(
            AsyncSessionAdapter(sync), requirement_id="req", files=files
        )
