"""Explicit opt-in MySQL/RustFS tests, exclusively in disposable databases/buckets."""

import asyncio
import hashlib
import os
import threading
import uuid
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from testing_agent.core.config import IntegrationExecutionSettings, load_settings
from testing_agent.core.errors import AppError
from testing_agent.core.object_storage import ObjectStorage
from testing_agent.models import Base
from testing_agent.models.bug import Bug
from testing_agent.models.bug_activity import BugActivity
from testing_agent.models.file_verification import FileVerification
from testing_agent.models.project import Project
from testing_agent.models.project_member import ProjectMember
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.stored_file import StoredFile
from testing_agent.models.user import User
from testing_agent.schemas.stored_file import FileUploadRequest
from testing_agent.services.database_snapshot import connect, identifier
from testing_agent.services.storage_backup import create_backup, restore_backup, verify_bundle
from testing_agent.services.stored_file import StoredFileService, utcnow

pytestmark = pytest.mark.skipif(
    os.getenv("CONTROL_PLANE_STORAGE_LIVE") != "1", reason="Requires explicit local storage opt-in"
)


class LiveEnvironment:
    # Keep service credentials out of pytest's fixture representation on failures.
    def __init__(self, settings, sessions):
        self.settings, self.sessions = settings, sessions

    def __iter__(self):
        return iter((self.settings, self.sessions))

    def __repr__(self):
        return "<isolated MySQL/RustFS environment>"


@pytest_asyncio.fixture
async def live():
    config = Path(__file__).resolve().parents[1] / "config" / "local.toml"
    original = load_settings(os.getenv("APP_CONF", str(config)))
    if not original.s3.enabled:
        pytest.fail("Live S3 is disabled")
    suffix = uuid.uuid4().hex[:12]
    database_names = ["s3_p1_test_" + suffix + role for role in ("_source", "_restore")]
    bucket_names = [name.replace("_", "-") for name in database_names]
    storage = ObjectStorage(original.s3)
    admin = connect(original.database_url)
    created_databases, created_buckets = [], []
    engine = None
    try:
        with admin.cursor() as cursor:
            for name in database_names:
                cursor.execute("CREATE DATABASE " + identifier(name) + " CHARACTER SET utf8mb4")
                created_databases.append(name)
        for name in bucket_names:
            storage.client.create_bucket(Bucket=name)
            created_buckets.append(name)
        settings = [
            replace(
                original,
                database_url=make_url(original.database_url)
                .set(database=database_names[index])
                .render_as_string(hide_password=False),
                s3=replace(original.s3, bucket=bucket_names[index], prefix="p1-audit"),
                integration_worker_key="isolated-restore-" + suffix
                if index == 1
                else original.integration_worker_key,
                integration_execution=IntegrationExecutionSettings(
                    enabled=False,
                    accept_submissions=False,
                    claim_enabled=False,
                    runtime_generation="isolated-restore-" + suffix,
                )
                if index == 1
                else original.integration_execution,
            )
            for index in range(2)
        ]
        engine = create_async_engine(settings[0].database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            session.add_all(
                [
                    User(user_id="owner", nickname="owner"),
                    User(user_id="viewer", nickname="viewer"),
                    Project(project_id="p", user_id="owner", name="isolated P1 audit"),
                ]
            )
            await session.flush()
            session.add(ProjectMember(project_id="p", user_id="viewer", role="viewer"))
            await session.commit()
        yield LiveEnvironment(settings, sessions)
    finally:
        if engine:
            await engine.dispose()
        # Only names successfully created by this fixture are ever removed.
        for bucket in created_buckets:
            for page in storage.client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
                for item in page.get("Contents", []):
                    storage.client.delete_object(Bucket=bucket, Key=item["Key"])
            storage.client.delete_bucket(Bucket=bucket)
        with admin.cursor() as cursor:
            for name in created_databases:
                cursor.execute("DROP DATABASE " + identifier(name))
        admin.close()


async def upload(files, content=b"Live S3 P1 evidence", purpose="attachment"):
    ticket = await files.initiate(
        "owner",
        FileUploadRequest(
            project_id="p",
            filename="evidence.txt",
            purpose=purpose,
            size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        ),
    )
    async with httpx.AsyncClient() as client:
        response = await client.post(
            ticket["upload"]["url"],
            data=ticket["upload"]["fields"],
            files={"file": ("evidence.txt", content)},
        )
    assert response.status_code == 204
    return ticket["fileId"]


async def downloaded(files, user, file_id):
    ticket = await files.download(user, file_id)
    async with httpx.AsyncClient() as client:
        response = await client.get(ticket["url"])
    assert response.status_code == 200
    assert hashlib.sha256(response.content).hexdigest() == ticket["sha256"]
    assert len(response.content) == ticket["size"]
    return response.content


async def create_evidence_bug(session):
    session.add(
        Bug(
            bug_id="audit-bug",
            project_id="p",
            bug_no=1,
            title="Evidence",
            found_sprint_id="audit-sprint",
        )
    )
    await session.commit()


@pytest.mark.parametrize("kind", ["requirement", "bug"])
async def test_live_deleted_business_denies_fresh_file_authorization(live, kind):
    settings, sessions = live
    async with sessions() as session:
        files = StoredFileService(session, settings[0].s3)
        if kind == "bug":
            await create_evidence_bug(session)
            entity = await session.scalar(select(Bug).where(Bug.bug_id == "audit-bug"))
            resource_id, purpose = "audit-bug", "attachment"
        else:
            session.add(
                Sprint(
                    sprint_id="audit-sprint",
                    project_id="p",
                    name="audit",
                    start_time=utcnow(),
                    end_time=utcnow() + timedelta(days=1),
                )
            )
            await session.flush()
            entity = Requirement(
                requirement_id="audit-requirement",
                sprint_id="audit-sprint",
                name="audit",
            )
            session.add(entity)
            await session.commit()
            resource_id, purpose = "audit-requirement", "requirement"
        file_id = await upload(files, purpose=purpose)
        await files.complete("owner", file_id)
        await files.attach("owner", file_id, "p", kind, resource_id, purpose=purpose)
        if kind == "requirement":
            entity.document_file_id = file_id
        await session.commit()
        assert await downloaded(files, "viewer", file_id) == b"Live S3 P1 evidence"
        previous = await files.download("viewer", file_id)
        await session.delete(entity)
        await session.commit()
        # A separate connection sees the committed deletion immediately.
        async with sessions() as reader:
            gateway = StoredFileService(reader, settings[0].s3)
            for operation in (gateway.metadata, gateway.download):
                with pytest.raises(AppError) as rejected:
                    await operation("viewer", file_id)
                assert rejected.value.http_code == 404
        # Existing signatures keep their bounded lifetime; no physical deletion.
        async with httpx.AsyncClient() as client:
            assert (await client.get(previous["url"])).status_code == 200


async def test_live_private_upload_integrity_permission_and_failure(live):
    settings, sessions = live
    async with sessions() as session:
        await create_evidence_bug(session)
        files = StoredFileService(session, settings[0].s3)
        file_id = await upload(files)
        await files.complete("owner", file_id)
        await files.attach("owner", file_id, "p", "bug", "audit-bug", purpose="attachment")
        await session.commit()
        assert await downloaded(files, "viewer", file_id) == b"Live S3 P1 evidence"
        row = await files.get(file_id)
        from botocore.auth import get_current_datetime

        with patch(
            "botocore.auth.get_current_datetime",
            return_value=get_current_datetime() - timedelta(hours=2),
        ):
            expired_url = files.storage.download_ticket(row.object_key, row.filename)
        still_valid_ticket = await files.download("viewer", file_id)
        async with httpx.AsyncClient() as client:
            unsigned = f"{settings[0].s3.endpoint}/{row.bucket}/{row.object_key}"
            assert (await client.get(unsigned)).status_code == 403
            expired = await client.get(expired_url)
            assert expired.status_code == 403
            assert "expired" in expired.text.lower()
        assert await downloaded(files, "viewer", file_id) == b"Live S3 P1 evidence"
        membership = await session.scalar(
            select(ProjectMember).where(ProjectMember.user_id == "viewer")
        )
        await session.delete(membership)
        await session.commit()
        with pytest.raises(AppError) as denied:
            await files.download("viewer", file_id)
        assert denied.value.http_code == 403
        async with httpx.AsyncClient() as client:
            assert (await client.get(still_valid_ticket["url"])).status_code == 200
        # Corrupt only this fixture's staging object. Completion must fail closed.
        bad = await upload(files)
        bad_row = await files.get(bad)
        files.storage.client.put_object(
            Bucket=bad_row.bucket, Key=bad_row.staging_key, Body=b"X" * bad_row.size
        )
        with pytest.raises(AppError, match="校验失败"):
            await files.complete("owner", bad)
        await session.rollback()
        missing = await upload(files)
        missing_row = await files.get(missing)
        files.storage.delete(missing_row.staging_key)
        with pytest.raises(AppError, match="尚未上传"):
            await files.complete("owner", missing)
        await session.rollback()
        row = await files.get(file_id)
        files.storage.delete(row.object_key)
        ticket = await files.download("owner", file_id)
        async with httpx.AsyncClient() as client:
            assert (await client.get(ticket["url"])).status_code == 404


async def test_live_cleanup_competing_instances_and_failure_recovery(live, monkeypatch, caplog):
    settings, sessions = live
    async with sessions() as session:
        files = StoredFileService(session, settings[0].s3)
        file_id = await upload(files)
        row = await files.get(file_id)
        row.expires_at = utcnow() - timedelta(hours=1)
        await session.commit()
        original_delete = files.storage.delete
        failed_once = False

        def fail_once(key):
            nonlocal failed_once
            if not failed_once:
                failed_once = True
                raise OSError("simulated network interruption")
            original_delete(key)

        monkeypatch.setattr(files.storage, "delete", fail_once)
        assert await files.cleanup() == {"deleted": 0, "failed": 1}
        assert file_id in caplog.text
        assert (await files.get(file_id)).status == "deleting"
        await session.rollback()

    async def clean():
        async with sessions() as session:
            return await StoredFileService(session, settings[0].s3).cleanup()

    results = await asyncio.gather(clean(), clean())
    assert sum(result["deleted"] for result in results) == 1
    assert sum(result["failed"] for result in results) == 0
    async with sessions() as session:
        assert await session.scalar(select(StoredFile).where(StoredFile.file_id == file_id)) is None


async def test_live_backup_restore_references_and_hashes(live, tmp_path):
    settings, sessions = live
    async with sessions() as session:
        files = StoredFileService(session, settings[0].s3)
        file_id = await upload(files)
        await files.complete("owner", file_id)
        await files.attach("owner", file_id, "p", "bug", "audit-bug", purpose="attachment")
        row = await files.get(file_id)
        row.status = "archived"
        row.expires_at = utcnow() - timedelta(hours=1)
        session.add(
            Sprint(
                sprint_id="audit-sprint",
                project_id="p",
                name="audit",
                start_time=utcnow(),
                end_time=utcnow() + timedelta(days=1),
            )
        )
        session.add(
            Bug(
                bug_id="audit-bug",
                bug_no=1,
                project_id="p",
                title="Historical evidence",
                found_sprint_id="audit-sprint",
                description_html="<p>Current description</p>",
            )
        )
        await session.flush()
        historical_html = f'<p>History</p><img data-file-id="{file_id}" />'
        session.add(
            BugActivity(
                activity_id="audit-activity",
                bug_id="audit-bug",
                kind="update",
                detail_json={"oldHtml": historical_html},
            )
        )
        await session.commit()
        assert await files.cleanup() == {"deleted": 0, "failed": 0}
        assert await downloaded(files, "viewer", file_id) == b"Live S3 P1 evidence"
        requirement_file_id = await upload(files, b"Requirement source", purpose="requirement")
        await files.complete("owner", requirement_file_id)
        await files.attach(
            "owner",
            requirement_file_id,
            "p",
            "requirement",
            "audit-requirement",
            purpose="requirement",
        )
        session.add(
            Requirement(
                requirement_id="audit-requirement",
                sprint_id="audit-sprint",
                name="Audit requirement",
                document_file_id=requirement_file_id,
                document_type="text",
            )
        )
        await session.commit()
        leased = await files.get(file_id)
        leased.cleanup_id = "source-cleaner"
        leased.cleanup_until = utcnow() + timedelta(minutes=5)
        session.add(
            FileVerification(
                operation_id="interrupted-verify",
                file_id="missing-source-file",
                bucket=settings[0].s3.bucket,
                object_key="p1-audit/interrupted-object",
                state="running",
                deadline=utcnow() + timedelta(minutes=10),
                gc_after=utcnow() + timedelta(minutes=10),
            )
        )
        await session.commit()
    # Fixture writers have stopped; use a real MySQL read lock while copying RustFS.
    bundle = tmp_path / "bundle"
    summary = await asyncio.to_thread(create_backup, settings[0], bundle)
    assert summary["referencedFiles"] == 2
    assert summary["tables"] == len(Base.metadata.tables)
    restored = await asyncio.to_thread(restore_backup, settings[1], bundle)
    assert restored == summary
    engine = create_async_engine(settings[1].database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            files = StoredFileService(session, settings[1].s3)
            operations = list(await session.scalars(select(FileVerification)))
            assert all(item.bucket == settings[1].s3.bucket for item in operations)
            interrupted = next(
                item for item in operations if item.operation_id == "interrupted-verify"
            )
            assert interrupted.state == "abandoned" and interrupted.settled_at is None
            row = await files.get(file_id)
            assert (row.resource_type, row.resource_id, row.status) == (
                "bug",
                "audit-bug",
                "archived",
            )
            assert row.bucket == settings[1].s3.bucket
            assert row.cleanup_id == "" and row.cleanup_until is None
            assert await downloaded(files, "viewer", file_id) == b"Live S3 P1 evidence"
            activity = await session.scalar(
                select(BugActivity).where(BugActivity.activity_id == "audit-activity")
            )
            assert activity.detail_json == {"oldHtml": historical_html}
            requirement = await session.scalar(
                select(Requirement).where(Requirement.requirement_id == "audit-requirement")
            )
            assert requirement.document_file_id == requirement_file_id
            assert (
                await downloaded(files, "viewer", requirement.document_file_id)
                == b"Requirement source"
            )
        with pytest.raises(ValueError, match="empty"):
            await asyncio.to_thread(restore_backup, settings[1], bundle)
        manifest = verify_bundle(bundle)
        object_path = bundle / manifest["objects"][0]["path"]
        object_path.write_bytes(b"corrupted backup")
        with pytest.raises(ValueError, match="checksum"):
            verify_bundle(bundle)
    finally:
        await engine.dispose()


async def test_live_restored_queue_is_quarantined_after_source_confirms_remote_success(
    live, tmp_path
):
    from support.integration_jobs import claim, prepare, result, submission

    from testing_agent.api.deps import build_integration_bug_service
    from testing_agent.models.integration_job import (
        IntegrationJob,
        IntegrationJobStep,
        IntegrationRuntime,
    )
    from testing_agent.repositories.integration_job import IntegrationJobRepository
    from testing_agent.services.integration_job import IntegrationJobService, no_change

    settings, sessions = live
    source_runtime = settings[0].integration_execution.runtime_generation or "source-runtime"
    async with sessions() as session:
        await create_evidence_bug(session)
        service = IntegrationJobService(
            IntegrationJobRepository(session),
            authorize=no_change,
            validate_prepare=no_change,
            apply_result=no_change,
            runtime_generation=source_runtime,
        )
        body = submission(
            bug_id="audit-bug",
            actor_user_id="owner",
            steps=[
                {"step_key": "create_bug", "kind": "create_bug"},
            ],
        )
        job = await service.submit(body)
        job_id = job.job_id
        await session.commit()
    # The backup sees queued; the source subsequently accepts a successful remote result.
    bundle = tmp_path / "integration-bundle"
    await asyncio.to_thread(create_backup, settings[0], bundle)
    async with sessions() as session:
        service = IntegrationJobService(
            IntegrationJobRepository(session),
            authorize=no_change,
            validate_prepare=no_change,
            apply_result=no_change,
            runtime_generation=source_runtime,
        )
        await service.claim(claim())
        permit = await service.prepare(
            job_id, "create_bug", prepare(runtime_generation=source_runtime)
        )
        await service.result(
            job_id,
            "create_bug",
            result(
                permit["operationId"],
                runtime_generation=source_runtime,
            ),
        )
        await session.commit()
        assert (await service.repository.get(job_id)).status == "succeeded"
    await asyncio.to_thread(restore_backup, settings[1], bundle)
    restored_engine = create_async_engine(settings[1].database_url)
    try:
        async with async_sessionmaker(restored_engine, expire_on_commit=False)() as session:
            job = await session.scalar(
                select(IntegrationJob).where(IntegrationJob.job_id == job_id)
            )
            assert job.status == "quarantined" and job.recovery_required
            assert job.active_scope is None and job.active_target is None
            step = await session.scalar(
                select(IntegrationJobStep).where(IntegrationJobStep.job_id == job_id)
            )
            assert step.status == "pending" and not step.operation_id
            runtime = await session.get(IntegrationRuntime, 1)
            assert runtime.blocked
            for config, expected_code in (
                (replace(settings[0], database_url=settings[1].database_url), 401),
                (settings[1], 409),
                (
                    replace(
                        settings[1],
                        integration_execution=replace(
                            settings[1].integration_execution,
                            enabled=True,
                            accept_submissions=True,
                            claim_enabled=True,
                            all_projects=True,
                        ),
                    ),
                    409,
                ),
            ):
                with pytest.raises(AppError) as denied:
                    await build_integration_bug_service(session, config).claim(claim())
                assert denied.value.http_code == expected_code
                await session.rollback()
            assert (
                await session.scalar(select(IntegrationJob).where(IntegrationJob.job_id == job_id))
            ).status == "quarantined"
    finally:
        await restored_engine.dispose()


async def test_live_cleanup_skips_active_verification(live, monkeypatch):
    settings, sessions = live
    entered, release = threading.Event(), threading.Event()
    async with sessions() as session:
        await create_evidence_bug(session)
        files = StoredFileService(session, settings[0].s3)
        file_id = await upload(files)
        seal = files.storage.seal

        def blocked_seal(*args, **kwargs):
            entered.set()
            if not release.wait(10):
                raise TimeoutError("test seal gate")
            return seal(*args, **kwargs)

        monkeypatch.setattr(files.storage, "seal", blocked_seal)
        completing = asyncio.create_task(files.complete("owner", file_id))
        assert await asyncio.to_thread(entered.wait, 10)
        real_now = utcnow
        monkeypatch.setattr(
            "testing_agent.services.stored_file_cleanup.utcnow",
            lambda: real_now() + timedelta(days=3),
        )
        try:
            async with sessions() as other:
                result = await StoredFileService(other, settings[0].s3).cleanup()
                assert result == {"deleted": 0, "failed": 0}
        finally:
            monkeypatch.setattr("testing_agent.services.stored_file_cleanup.utcnow", real_now)
            release.set()
            await completing
        await files.attach("owner", file_id, "p", "bug", "audit-bug", purpose="attachment")
        await session.commit()
        assert await downloaded(files, "viewer", file_id) == b"Live S3 P1 evidence"


async def test_live_failed_save_and_attachment_lock_survive_cleanup(live, monkeypatch):
    settings, sessions = live
    async with sessions() as session:
        await create_evidence_bug(session)
        files = StoredFileService(session, settings[0].s3)
        file_id = await upload(files)
        await files.complete("owner", file_id)
        await files.attach("owner", file_id, "p", "bug", "audit-bug", purpose="attachment")
        # The business save fails: the file remains ready and retryable after rollback.
        await session.rollback()
        assert (await files.get(file_id)).status == "ready"
        with pytest.raises(AppError):
            await files.download("viewer", file_id)
        await files.attach("owner", file_id, "p", "bug", "audit-bug", purpose="attachment")
        real_now = utcnow
        monkeypatch.setattr(
            "testing_agent.services.stored_file_cleanup.utcnow",
            lambda: real_now() + timedelta(days=3),
        )
        try:
            async with sessions() as other:
                assert await StoredFileService(other, settings[0].s3).cleanup() == {
                    "deleted": 0,
                    "failed": 0,
                }
        finally:
            monkeypatch.setattr("testing_agent.services.stored_file_cleanup.utcnow", real_now)
        await session.commit()
        assert await downloaded(files, "viewer", file_id) == b"Live S3 P1 evidence"


async def test_live_queue_claims_are_unique_and_expired_leases_fail_closed(live):
    from testing_agent.models.ui_test_case import UiTestCase
    from testing_agent.models.ui_test_case_run import UiTestCaseRun
    from testing_agent.models.ui_test_suite import UiTestSuite
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.repositories.worker_task import WorkerTaskRepository
    from testing_agent.schemas.workers import WorkerClaimRequest
    from testing_agent.services.worker_task import WorkerTaskService

    _, sessions = live
    async with sessions() as session:
        session.add(
            Sprint(
                sprint_id="s",
                project_id="p",
                name="s",
                start_time=utcnow(),
                end_time=utcnow() + timedelta(days=1),
            )
        )
        await session.flush()
        session.add(Requirement(requirement_id="r", sprint_id="s", name="r"))
        await session.flush()
        session.add(UiTestSuite(suite_id="suite", requirement_id="r", name="suite"))
        await session.flush()
        session.add(UiTestCase(case_id="case", suite_id="suite", name="case", steps_json=[]))
        await session.flush()
        for index in range(2):
            session.add(
                UiTestCaseRun(
                    run_id=f"run-{index}", case_id="case", suite_id="suite", trigger_user_id="owner"
                )
            )
            session.add(
                WorkerTask(
                    domain="ui",
                    task_id=f"task-{index}",
                    task_type="case_debug",
                    run_id=f"run-{index}",
                )
            )
        await session.commit()

    async def claim(worker):
        async with sessions() as session:
            return await WorkerTaskService(WorkerTaskRepository(session)).claim(
                "ui", WorkerClaimRequest(workerId=worker)
            )

    claims = await asyncio.gather(claim("worker-1"), claim("worker-2"))
    assert {claim["taskId"] for claim in claims} == {"task-0", "task-1"}
    assert await claim("worker-3") is None
    async with sessions() as session:
        for task in await session.scalars(select(WorkerTask)):
            task.lease_expires_at = utcnow() - timedelta(seconds=1)
        await session.commit()
        await WorkerTaskService(WorkerTaskRepository(session)).expire_leases("ui")
        assert {task.status for task in await session.scalars(select(WorkerTask))} == {"failed"}
        assert {run.status for run in await session.scalars(select(UiTestCaseRun))} == {"failed"}
    assert await claim("worker-4") is None


async def test_live_skill_batches_keep_previous_signed_content_and_cleanup_safely(live, tmp_path):
    from testing_agent.services.builtin_skills import sync_builtin_skills

    settings, sessions = live
    folder = tmp_path / "builtin"
    folder.mkdir()
    source = folder / "SKILL.md"
    source.write_bytes(b"old default")
    async with sessions() as session:
        files = StoredFileService(session, settings[0].s3)
        await sync_builtin_skills(files, tmp_path)
        from testing_agent.models.project_skill_space import ProjectSkillSpace

        skill = await session.scalar(
            select(ProjectSkillSpace).where(ProjectSkillSpace.filename == "builtin")
        )
        old_id = skill.manifest[0]["fileId"]
        old = await files.get(old_id)
        old_key = old.object_key
        old_ticket = await files.ticket(old)
        await session.commit()
        source.write_bytes(b"new default")
        await sync_builtin_skills(files, tmp_path)
        skill = await session.scalar(
            select(ProjectSkillSpace)
            .where(ProjectSkillSpace.filename == "builtin")
            .execution_options(populate_existing=True)
        )
        current = await files.get(skill.manifest[0]["fileId"])
        assert current.object_key != old_key
        new_ticket = await files.ticket(current)
        await session.commit()
        async with httpx.AsyncClient() as client:
            assert (await client.get(old_ticket["url"])).content == b"old default"
            assert (await client.get(new_ticket["url"])).content == b"new default"
        old = await files.get(old_id)
        old.expires_at = utcnow() - timedelta(seconds=1)
        await session.commit()
        assert (await files.cleanup())["deleted"] == 1
        async with httpx.AsyncClient() as client:
            assert (await client.get(new_ticket["url"])).content == b"new default"
