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
from testing_agent.models.project_skill_space import ProjectSkillSpace
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
            await session.execute(delete(ProjectSkillSpace))
            await session.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_mysql_skill_publication_and_cleanup_do_not_hold_scope_or_file_locks(mysql):
    from testing_agent.schemas.project_skill_space import ProjectSkillUploadRequest
    from testing_agent.services.skill_storage import SkillPublisher

    with mysql.begin() as connection:
        user = seed_row(connection, User.__table__, {"status": "active"})
        project = seed_row(connection, Project.__table__, {"user_id": user["user_id"]})
        skill_file = seed_row(
            connection,
            StoredFile.__table__,
            {
                "project_id": project["project_id"],
                "uploaded_by": user["user_id"],
                "filename": "SKILL.md",
                "status": "ready",
                "purpose": "project_skill",
                "size": 5,
                "sha256": hashlib.sha256(b"hello").hexdigest(),
                "bucket": "isolated-d3b",
                "object_key": "private/SKILL.md",
                "staging_key": "",
                "expires_at": utcnow() + timedelta(hours=1),
            },
        )
        expired = seed_row(
            connection,
            StoredFile.__table__,
            {
                "project_id": project["project_id"],
                "uploaded_by": user["user_id"],
                "filename": "old.txt",
                "status": "pending",
                "purpose": "requirement",
                "bucket": "isolated-d3b",
                "object_key": "private/old.txt",
                "staging_key": "",
                "expires_at": utcnow() - timedelta(hours=1),
            },
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    started, release = asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()
    settings = ObjectStorageSettings(
        enabled=True, bucket="isolated-d3b", access_key="test", secret_key="test"
    )

    class SlowStorage:
        def seal(self, *args, **kwargs):
            loop.call_soon_threadsafe(started.set)
            assert release.wait(10)

        def delete(self, key):
            loop.call_soon_threadsafe(started.set)
            assert release.wait(10)

    task = None
    try:
        async with sessions() as session:
            files = StoredFileService(session, settings, SlowStorage())
            request = ProjectSkillUploadRequest(
                name="custom", files=[{"path": "SKILL.md", "fileId": skill_file["file_id"]}]
            )
            task = asyncio.create_task(
                SkillPublisher(files).project(project["project_id"], request, user["user_id"])
            )
            await asyncio.wait_for(started.wait(), 5)
            assert not session.in_transaction()
            async with sessions() as other:
                await asyncio.wait_for(
                    other.scalar(
                        select(Project)
                        .where(Project.project_id == project["project_id"])
                        .with_for_update()
                    ),
                    2,
                )
                row = await asyncio.wait_for(
                    other.scalar(
                        select(StoredFile)
                        .where(StoredFile.file_id == skill_file["file_id"])
                        .with_for_update()
                    ),
                    2,
                )
                assert row.object_key == "private/SKILL.md" and row.status == "ready"
                await other.commit()
            release.set()
            assert (await asyncio.wait_for(task, 5)).filename == "custom"
            release.clear()
            started.clear()
            task = asyncio.create_task(files.cleanup())
            await asyncio.wait_for(started.wait(), 5)
            assert not session.in_transaction()
            async with sessions() as other:
                row = await asyncio.wait_for(
                    other.scalar(
                        select(StoredFile)
                        .where(StoredFile.file_id == expired["file_id"])
                        .with_for_update()
                    ),
                    2,
                )
                assert row.status == "deleting" and row.cleanup_id
                await other.commit()
                assert await StoredFileService(other, settings, SlowStorage()).cleanup() == {
                    "deleted": 0,
                    "failed": 0,
                }
            release.set()
            assert await asyncio.wait_for(task, 5) == {"deleted": 1, "failed": 0}
    finally:
        release.set()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        async with sessions() as session:
            await session.execute(delete(FileVerification))
            await session.execute(delete(ProjectSkillSpace))
            await session.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_mysql_late_skill_copy_cannot_replace_a_concurrent_publication(mysql):
    from testing_agent.schemas.project_skill_space import ProjectSkillUploadRequest
    from testing_agent.services.skill_storage import SkillPublisher

    with mysql.begin() as connection:
        user = seed_row(connection, User.__table__, {"status": "active"})
        project = seed_row(connection, Project.__table__, {"user_id": user["user_id"]})
        records = [
            seed_row(
                connection,
                StoredFile.__table__,
                {
                    "project_id": project["project_id"],
                    "uploaded_by": user["user_id"],
                    "filename": "SKILL.md",
                    "status": "ready",
                    "purpose": "project_skill",
                    "size": 5,
                    "sha256": hashlib.sha256(b"hello").hexdigest(),
                    "bucket": "isolated-skill-race",
                    "object_key": f"private/{index}/SKILL.md",
                    "staging_key": "",
                    "expires_at": utcnow() + timedelta(hours=1),
                },
            )
            for index in range(2)
        ]
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    started, release = asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()
    calls = []
    settings = ObjectStorageSettings(
        enabled=True, bucket="isolated-skill-race", access_key="test", secret_key="test"
    )

    class Storage:
        def seal(self, source, target, *args, **kwargs):
            calls.append(target)
            if source == records[0]["object_key"]:
                loop.call_soon_threadsafe(started.set)
                assert release.wait(10)

    task = None
    try:
        async with sessions() as first, sessions() as second:
            first_files = StoredFileService(first, settings, Storage())
            second_files = StoredFileService(second, settings, Storage())
            requests = [
                ProjectSkillUploadRequest(
                    name="race", files=[{"path": "SKILL.md", "fileId": row["file_id"]}]
                )
                for row in records
            ]
            task = asyncio.create_task(
                SkillPublisher(first_files).project(
                    project["project_id"], requests[0], user["user_id"]
                )
            )
            await asyncio.wait_for(started.wait(), 5)
            winner = await asyncio.wait_for(
                SkillPublisher(second_files).project(
                    project["project_id"], requests[1], user["user_id"]
                ),
                5,
            )
            release.set()
            with pytest.raises(AppError) as conflict:
                await asyncio.wait_for(task, 5)
            assert conflict.value.http_code == 409
            current = await first.scalar(
                select(ProjectSkillSpace).where(
                    ProjectSkillSpace.skill_space_id == winner.skill_space_id
                )
            )
            assert current.manifest[0]["fileId"] == records[1]["file_id"]
            assert len(set(calls)) == 2
            assert (await first_files.get(records[0]["file_id"])).status == "ready"
    finally:
        release.set()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        async with sessions() as session:
            await session.execute(delete(FileVerification))
            await session.execute(delete(ProjectSkillSpace))
            await session.commit()
        await engine.dispose()
