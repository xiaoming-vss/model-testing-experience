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
from testing_agent.models.project_skill_space import ProjectSkillSpace
from testing_agent.schemas.project_skill_space import ProjectSkillUploadRequest
from testing_agent.services.file_verification import FileVerificationWorkflow
from testing_agent.services.skill_storage import SkillPublisher
from testing_agent.services.stored_file import StoredFileService, utcnow


async def body(files, content):
    row, _ = await upload(files, content, "SKILL.md", "project_skill")
    await files.complete("owner", row.file_id)
    return ProjectSkillUploadRequest(
        name="custom", files=[{"path": "SKILL.md", "fileId": row.file_id}]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["permission", "concurrent_publish"])
async def test_skill_copy_has_no_transaction_and_rechecks_publication(files, monkeypatch, change):
    publisher = SkillPublisher(files)
    initial = await publisher.project("p", await body(files, b"old"), "owner")
    initial_hash, skill_id = initial.hash, initial.skill_space_id
    request = await body(files, b"first")
    started, release = asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()
    original = files.storage.seal
    copies = []

    def seal(*args, **kwargs):
        assert not files.session.in_transaction()
        if "/skills/projects/" in args[1]:
            copies.append(args[1])
            if len(copies) == 1:
                loop.call_soon_threadsafe(started.set)
                assert release.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(files.storage, "seal", seal)
    task = asyncio.create_task(publisher.project("p", request, "owner"))
    try:
        await asyncio.wait_for(started.wait(), 3)
        async with async_sessionmaker(files.session.bind, expire_on_commit=False)() as session:
            current = await session.scalar(
                select(ProjectSkillSpace).where(ProjectSkillSpace.skill_space_id == skill_id)
            )
            assert current.hash == initial_hash
            if change == "permission":
                project = await session.scalar(select(Project).where(Project.project_id == "p"))
                project.user_id = "member"
                await session.commit()
                expected = initial_hash
            else:
                other = StoredFileService(session, files.settings, files.storage)
                published = await SkillPublisher(other).project(
                    "p", await body(other, b"second"), "owner"
                )
                expected = published.hash
        release.set()
        with pytest.raises(AppError) as rejected:
            await task
        assert rejected.value.http_code == (403 if change == "permission" else 409)
        current = await files.session.scalar(
            select(ProjectSkillSpace)
            .where(ProjectSkillSpace.skill_space_id == skill_id)
            .execution_options(populate_existing=True)
        )
        assert current.hash == expected
        operations = list(
            await files.session.scalars(
                select(FileVerification).where(FileVerification.object_key.in_(copies))
            )
        )
        assert sum(op.state == "discarded" for op in operations) == 1
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_uncertain_copy_retains_tombstone_and_does_not_change_current_skill(
    files, monkeypatch
):
    publisher = SkillPublisher(files)
    skill = await publisher.project("p", await body(files, b"old"), "owner")
    old_hash, skill_id = skill.hash, skill.skill_space_id
    request = await body(files, b"new")
    original = files.storage.seal

    def timeout(*args, **kwargs):
        original(*args, **kwargs)
        raise TimeoutError("receipt lost")

    monkeypatch.setattr(files.storage, "seal", timeout)
    with pytest.raises(TimeoutError):
        await publisher.project("p", request, "owner")
    operation = await files.session.scalar(
        select(FileVerification).where(FileVerification.state == "abandoned")
    )
    assert operation is not None and operation.settled_at is None
    operation.gc_after = utcnow() - timedelta(seconds=1)
    await files.session.commit()
    await FileVerificationWorkflow(files.session, files.settings, files.storage).collect()
    assert (
        await files.session.scalar(
            select(FileVerification).where(FileVerification.operation_id == operation.operation_id)
        )
        is not None
    )
    current = await files.session.scalar(
        select(ProjectSkillSpace)
        .where(ProjectSkillSpace.skill_space_id == skill_id)
        .execution_options(populate_existing=True)
    )
    assert current.hash == old_hash


@pytest.mark.asyncio
async def test_cancelled_skill_copy_is_fenced_and_late_object_remains_reclaimable(
    files, monkeypatch
):
    publisher = SkillPublisher(files)
    skill = await publisher.project("p", await body(files, b"old"), "owner")
    skill_id, original_hash = skill.skill_space_id, skill.hash
    request = await body(files, b"new")
    started, finished, release = asyncio.Event(), asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()
    original = files.storage.seal

    def seal(*args, **kwargs):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(10)
        try:
            return original(*args, **kwargs)
        finally:
            loop.call_soon_threadsafe(finished.set)

    monkeypatch.setattr(files.storage, "seal", seal)
    task = asyncio.create_task(publisher.project("p", request, "owner"))
    try:
        await asyncio.wait_for(started.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        operation = await files.session.scalar(
            select(FileVerification).where(FileVerification.state == "running")
        )
        operation.deadline = operation.gc_after = utcnow() - timedelta(seconds=1)
        await files.session.commit()
        collector = FileVerificationWorkflow(files.session, files.settings, files.storage)
        await collector.collect()
        assert operation.state == "abandoned" and operation.settled_at is None
        release.set()
        await asyncio.wait_for(finished.wait(), 3)
        assert (
            files.storage.client.head_object(Bucket=operation.bucket, Key=operation.object_key)[
                "ContentLength"
            ]
            == 3
        )
        operation.gc_after = utcnow() - timedelta(seconds=1)
        await files.session.commit()
        await collector.collect()
        with pytest.raises(files.storage.client.exceptions.ClientError):
            files.storage.client.head_object(Bucket=operation.bucket, Key=operation.object_key)
        current = await files.session.scalar(
            select(ProjectSkillSpace)
            .where(ProjectSkillSpace.skill_space_id == skill_id)
            .execution_options(populate_existing=True)
        )
        assert current.hash == original_hash
    finally:
        release.set()
        await asyncio.wait_for(finished.wait(), 3)
