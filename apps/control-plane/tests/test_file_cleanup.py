import asyncio
import threading
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from support.stored_files import files as files
from support.stored_files import upload

from testing_agent.core.errors import AppError
from testing_agent.models.stored_file import StoredFile
from testing_agent.services.stored_file import StoredFileService, utcnow
from testing_agent.services.stored_file_cleanup import StoredFileCleanup


@pytest.mark.asyncio
async def test_cleanup_releases_transaction_and_excludes_other_cleaners_and_attach(
    files, monkeypatch
):
    row, _ = await upload(files)
    await files.complete("owner", row.file_id)
    file_id = row.file_id
    row.expires_at = utcnow() - timedelta(hours=1)
    await files.session.commit()
    started, release = asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()
    original = files.storage.delete
    calls = []

    def delete(key):
        assert not files.session.in_transaction()
        calls.append(key)
        if len(calls) == 1:
            loop.call_soon_threadsafe(started.set)
            assert release.wait(10)
        return original(key)

    monkeypatch.setattr(files.storage, "delete", delete)
    task = asyncio.create_task(files.cleanup())
    try:
        await asyncio.wait_for(started.wait(), 3)
        async with async_sessionmaker(files.session.bind, expire_on_commit=False)() as session:
            other = StoredFileService(session, files.settings, files.storage)
            assert await other.cleanup() == {"deleted": 0, "failed": 0}
            with pytest.raises(AppError):
                await other.attach("owner", file_id, "p", "requirement", "r", purpose="requirement")
            await session.rollback()
        release.set()
        assert await task == {"deleted": 1, "failed": 0}
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_expired_cleanup_claim_recovery_rejects_old_receipt(files):
    row, _ = await upload(files)
    file_id = row.file_id
    row.expires_at = utcnow() - timedelta(hours=1)
    await files.session.commit()
    cleaner = StoredFileCleanup(files.session, files.settings, files.storage)
    old = (await cleaner.claim(staging=False))[0]
    row = await files.get(file_id)
    row.cleanup_until = utcnow() - timedelta(seconds=1)
    await files.session.commit()
    current = (await cleaner.claim(staging=False))[0]
    assert old.generation != current.generation
    assert not await cleaner.finish(old)
    assert await cleaner.run_claims([old]) == (0, 0)
    assert (await files.get(file_id)).cleanup_id == current.generation
    await files.session.commit()
    assert await cleaner.run_claims([current]) == (1, 0)
    assert (
        await files.session.scalar(select(StoredFile).where(StoredFile.file_id == file_id)) is None
    )


@pytest.mark.asyncio
async def test_expired_unverified_bug_upload_is_not_promoted_to_history(files):
    row, _ = await upload(files, purpose="attachment")
    file_id = row.file_id
    row.resource_type, row.resource_id = "bug", "bug-1"
    row.expires_at = utcnow() - timedelta(hours=1)
    await files.session.commit()
    assert await files.cleanup() == {"deleted": 1, "failed": 0}
    assert (
        await files.session.scalar(select(StoredFile).where(StoredFile.file_id == file_id)) is None
    )


def test_migration_refuses_to_drop_an_active_cleanup_claim():
    import sqlalchemy as sa
    from support.initial_schema_migration import migration_config

    from alembic import command

    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        config = migration_config(connection)
        command.upgrade(config, "head")
        connection.execute(
            StoredFile.__table__.insert().values(
                file_id="claimed",
                project_id="project",
                uploaded_by="owner",
                filename="a.txt",
                content_type="text/plain",
                size=1,
                sha256="a" * 64,
                bucket="test",
                object_key="private/a.txt",
                staging_key="",
                status="deleting",
                purpose="attachment",
                expires_at=utcnow(),
                cleanup_id="active-claim",
                cleanup_until=utcnow(),
            )
        )
        connection.commit()
        with pytest.raises(RuntimeError, match="Stop and drain"):
            command.downgrade(config, "20261021_0046")
        connection.rollback()
        assert connection.scalar(select(StoredFile.cleanup_id)) == "active-claim"
    engine.dispose()
