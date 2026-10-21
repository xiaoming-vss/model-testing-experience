"""Exercise cancellation, current authority and fencing through the real completion entry."""

import asyncio
import threading
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from support.stored_files import files as files
from support.stored_files import upload

from testing_agent.core.errors import AppError
from testing_agent.models.file_verification import FileVerification
from testing_agent.models.project import Project
from testing_agent.models.user import User
from testing_agent.services.file_verification import FileVerificationWorkflow, now_utc
from testing_agent.services.stored_file import StoredFileService


def blocked_seal(files, monkeypatch):
    started, finished = asyncio.Event(), asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    original = files.storage.seal
    calls = []

    def seal(*args, **kwargs):
        assert not files.session.in_transaction()
        calls.append(args[1])
        if len(calls) == 1:
            loop.call_soon_threadsafe(started.set)
            assert release.wait(10), "test did not release storage"
        try:
            return original(*args, **kwargs)
        finally:
            loop.call_soon_threadsafe(finished.set)

    monkeypatch.setattr(files.storage, "seal", seal)
    return started, finished, release, calls


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["account_disabled", "ownership_transferred"])
async def test_completion_rechecks_account_after_storage_without_transaction(
    files, monkeypatch, change
):
    row, _ = await upload(files)
    file_id = row.file_id
    started, _, release, _ = blocked_seal(files, monkeypatch)
    work = asyncio.create_task(files.complete("owner", file_id))
    try:
        await asyncio.wait_for(started.wait(), 3)
        async with async_sessionmaker(files.session.bind, expire_on_commit=False)() as other:
            if change == "account_disabled":
                user = await other.scalar(select(User).where(User.user_id == "owner"))
                user.status = "disabled"
            else:
                project = await other.scalar(select(Project).where(Project.project_id == "p"))
                project.user_id = "member"
            await other.commit()
        release.set()
        with pytest.raises(AppError) as denied:
            await work
        assert denied.value.http_code == 403
        row = await files.get(file_id)
        assert row.status == "pending" and row.verification_id == ""
        operation = await files.session.scalar(select(FileVerification))
        assert operation.state == "discarded" and operation.settled_at is not None
    finally:
        release.set()
        await asyncio.gather(work, return_exceptions=True)


@pytest.mark.asyncio
async def test_expired_writer_cannot_publish_after_new_generation(files, monkeypatch):
    row, _ = await upload(files)
    file_id = row.file_id
    started, _, release, calls = blocked_seal(files, monkeypatch)
    work = asyncio.create_task(files.complete("owner", file_id))
    try:
        await asyncio.wait_for(started.wait(), 3)
        async with async_sessionmaker(files.session.bind, expire_on_commit=False)() as other:
            service = StoredFileService(other, files.settings, files.storage)
            with pytest.raises(AppError, match="正在核验"):
                await service.complete("owner", file_id)
            operation = await other.scalar(select(FileVerification))
            operation.deadline = now_utc() - timedelta(seconds=1)
            await other.commit()
            await service.complete("owner", file_id)
            newest = await service.get(file_id)
            published_key = newest.object_key
            await other.commit()
        release.set()
        with pytest.raises(AppError, match="已失效"):
            await work
        newest = await files.get(file_id)
        assert newest.status == "ready" and newest.object_key == published_key
        assert len(set(calls)) == 2 and published_key == calls[1]
        operations = list(await files.session.scalars(select(FileVerification)))
        assert sorted(op.state for op in operations) == ["discarded", "published"]
    finally:
        release.set()
        await asyncio.gather(work, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_thread_late_write_keeps_reclaimable_tombstone(files, monkeypatch):
    row, _ = await upload(files)
    file_id = row.file_id
    started, finished, release, calls = blocked_seal(files, monkeypatch)
    work = asyncio.create_task(files.complete("owner", file_id))
    collector = FileVerificationWorkflow(files.session, files.settings, files.storage)
    try:
        await asyncio.wait_for(started.wait(), 3)
        work.cancel()
        with pytest.raises(asyncio.CancelledError):
            await work
        operation = await files.session.scalar(select(FileVerification))
        operation.deadline = operation.gc_after = now_utc() - timedelta(seconds=1)
        await files.session.commit()
        original_delete = files.storage.delete

        def delete(key):
            assert not files.session.in_transaction()
            return original_delete(key)

        monkeypatch.setattr(files.storage, "delete", delete)
        assert (await collector.collect())["deleted"] == 1
        assert operation.state == "abandoned" and operation.settled_at is None
        release.set()
        await asyncio.wait_for(finished.wait(), 3)
        assert (
            files.storage.client.head_object(Bucket=row.bucket, Key=calls[0])["ContentLength"] == 5
        )
        operation.gc_after = now_utc() - timedelta(seconds=1)
        await files.session.commit()
        assert (await collector.collect())["deleted"] == 1
        with pytest.raises(files.storage.client.exceptions.ClientError):
            files.storage.client.head_object(Bucket=row.bucket, Key=calls[0])
        assert (await files.get(file_id)).status == "pending"
        assert await files.session.scalar(select(FileVerification)) is not None
    finally:
        release.set()
        await asyncio.wait_for(finished.wait(), 3)


@pytest.mark.asyncio
async def test_failed_verification_garbage_is_removed_without_touching_published_file(files):
    row, _ = await upload(files)
    file_id = row.file_id
    files.storage.client.put_object(Bucket=row.bucket, Key=row.staging_key, Body=b"wrong")
    with pytest.raises(AppError, match="校验失败"):
        await files.complete("owner", file_id)
    files.storage.client.put_object(Bucket=row.bucket, Key=row.staging_key, Body=b"hello")
    await files.complete("owner", file_id)
    collector = FileVerificationWorkflow(files.session, files.settings, files.storage)
    assert await collector.collect() == {"deleted": 1, "failed": 0}
    current = await files.get(file_id)
    assert (
        files.storage.client.get_object(Bucket=row.bucket, Key=current.object_key)["Body"].read()
        == b"hello"
    )
    operations = list(await files.session.scalars(select(FileVerification)))
    assert len(operations) == 1 and operations[0].state == "published"


@pytest.mark.asyncio
async def test_worker_attachment_rechecks_authority_after_verification(files, monkeypatch):
    from types import SimpleNamespace

    from testing_agent.core.errors import ErrForbidden
    from testing_agent.handlers import worker_files

    row, _ = await upload(files, b"\x89PNG\r\n\x1a\n", "image.png", "ui_artifact")
    row.resource_type, row.resource_id = "ui_worker_task", "task"
    await files.session.commit()
    file_id = row.file_id
    calls = 0

    async def authority(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ErrForbidden()
        return SimpleNamespace(actor="owner", project_id="p")

    monkeypatch.setattr(worker_files, "authority", authority)
    with pytest.raises(AppError) as denied:
        await worker_files.complete_artifact(
            "task",
            file_id,
            worker_files.WorkerFileCompleteRequest(workerId="w"),
            service=None,
            files=files,
        )
    assert denied.value.http_code == 403 and calls == 2
    assert (await files.get(file_id)).status == "ready"


def test_migration_preserves_unsettled_verification_evidence():
    import sqlalchemy as sa
    from support.initial_schema_migration import migration_config

    from alembic import command

    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        config = migration_config(connection)
        command.upgrade(config, "head")
        connection.execute(
            FileVerification.__table__.insert().values(
                operation_id="interrupted",
                file_id="deleted-file",
                bucket="test",
                object_key="private/interrupted",
                state="abandoned",
                deadline=now_utc(),
                gc_after=now_utc(),
            )
        )
        connection.commit()
        with pytest.raises(RuntimeError, match="Preserve verification"):
            command.downgrade(config, "20261021_0045")
        connection.rollback()
        assert connection.scalar(select(FileVerification.operation_id)) == "interrupted"
    engine.dispose()
