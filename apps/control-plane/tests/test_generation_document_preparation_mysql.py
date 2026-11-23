"""File preparation holds no MySQL row locks and final validation catches races."""

import asyncio
import threading
from hashlib import sha256
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.domain.generation_root_fingerprints import IncompleteRootInput
from testing_agent.models import Base
from testing_agent.models.stored_file import StoredFile
from testing_agent.services.generation_document_preparation import (
    lock_prepared_requirement_root,
    prepare_requirement_document,
)


class BlockingStorage:
    def __init__(self, data):
        self.data = data
        self.started = threading.Event()
        self.release = threading.Event()

    def get_object(self, key):
        assert key == "original"
        self.started.set()
        if not self.release.wait(10):
            raise RuntimeError("test reader was not released")
        return {"Body": self}

    def iter_chunks(self, chunk_size):
        yield self.data

    def close(self):
        pass


def test_file_changed_during_external_read_is_rejected(mysql):  # noqa: F811
    tables = Base.metadata.tables
    data = b"<p>Requirement</p>"
    digest = sha256(data).hexdigest()
    with mysql.begin() as connection:
        project = seed_row(connection, tables["projects"])
        sprint = seed_row(connection, tables["sprints"], {"project_id": project["project_id"]})
        requirement = seed_row(
            connection,
            tables["requirements"],
            {
                "requirement_id": "req",
                "sprint_id": sprint["sprint_id"],
                "document_type": "richtext",
                "document_file_id": "document",
                "document_filename": "requirement.html",
                "document_hash": digest,
            },
        )
        seed_row(
            connection,
            tables["stored_files"],
            {
                "file_id": "document",
                "project_id": project["project_id"],
                "filename": "requirement.html",
                "size": len(data),
                "sha256": digest,
                "bucket": "bucket",
                "object_key": "original",
                "purpose": "requirement",
                "status": "attached",
                "resource_type": "requirement",
                "resource_id": requirement["requirement_id"],
            },
        )
    storage = BlockingStorage(data)
    files = SimpleNamespace(settings=SimpleNamespace(bucket="bucket"), storage=storage)

    async def run():
        engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as reader, factory() as editor:
                preparing = asyncio.create_task(
                    prepare_requirement_document(
                        reader,
                        requirement_id="req",
                        files=files,
                    )
                )
                assert await asyncio.to_thread(storage.started.wait, 10)
                try:
                    await asyncio.wait_for(
                        editor.execute(
                            sa.update(StoredFile)
                            .where(StoredFile.file_id == "document")
                            .values(object_key="replacement")
                        ),
                        timeout=5,
                    )
                    await editor.commit()
                finally:
                    storage.release.set()
                prepared = await asyncio.wait_for(preparing, timeout=10)
                await reader.rollback()
                with pytest.raises(IncompleteRootInput, match="changed during preparation"):
                    await lock_prepared_requirement_root(reader, prepared=prepared)
                await reader.rollback()
        finally:
            storage.release.set()
            await engine.dispose()

    asyncio.run(run())
