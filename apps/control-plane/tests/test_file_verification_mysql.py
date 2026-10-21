"""Real MySQL row-lock checks with deterministic slow storage."""

import asyncio
import hashlib
import threading
import time
from datetime import timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql as mysql
from support.mysql_initialization import seed_row

from testing_agent.core.errors import AppError
from testing_agent.core.object_storage import ObjectStorageSettings
from testing_agent.models.file_verification import FileVerification
from testing_agent.models.project import Project
from testing_agent.models.stored_file import StoredFile
from testing_agent.models.user import User
from testing_agent.services.stored_file import StoredFileService, utcnow


@pytest.mark.asyncio
async def test_mysql_verification_releases_locks_and_serializes_duplicate_claims(mysql):
    with mysql.begin() as connection:
        user = seed_row(connection, User.__table__, {"status": "active"})
        project = seed_row(connection, Project.__table__, {"user_id": user["user_id"]})
        record = seed_row(
            connection,
            StoredFile.__table__,
            {
                "project_id": project["project_id"],
                "uploaded_by": user["user_id"],
                "filename": "sample.txt",
                "status": "pending",
                "purpose": "requirement",
                "size": 5,
                "sha256": hashlib.sha256(b"hello").hexdigest(),
                "bucket": "disposable-test",
                "object_key": "sample/sample.txt",
                "staging_key": "sample/upload",
                "expires_at": utcnow() + timedelta(hours=1),
            },
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    calls = []

    class SlowStorage:
        def seal(self, staging, key, size, sha256, filename, **kwargs):
            calls.append(key)
            loop.call_soon_threadsafe(started.set)
            assert release.wait(10)

    settings = ObjectStorageSettings(
        enabled=True, bucket="disposable-test", access_key="test", secret_key="test"
    )
    task = None
    try:
        async with sessions() as session:
            files = StoredFileService(session, settings, SlowStorage())
            task = asyncio.create_task(files.complete(user["user_id"], record["file_id"]))
            await asyncio.wait_for(started.wait(), 5)
            assert not session.in_transaction()
            async with sessions() as second:
                start = time.perf_counter()
                row = await asyncio.wait_for(
                    second.scalar(
                        select(StoredFile)
                        .where(StoredFile.file_id == record["file_id"])
                        .with_for_update()
                    ),
                    2,
                )
                assert time.perf_counter() - start < 2
                assert row.status == "pending" and row.verification_id
                await second.commit()
                with pytest.raises(AppError, match="正在核验"):
                    await StoredFileService(second, settings, SlowStorage()).complete(
                        user["user_id"], record["file_id"]
                    )
            release.set()
            assert (await asyncio.wait_for(task, 5))["status"] == "ready"
            assert len(calls) == 1
    finally:
        release.set()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        async with sessions() as session:
            await session.execute(delete(FileVerification))
            await session.commit()
        await engine.dispose()
