import hashlib
from datetime import timedelta

import pytest
import pytest_asyncio
from moto import mock_aws
from sqlalchemy import select
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from testing_agent.core.errors import AppError
from testing_agent.core.object_storage import ObjectStorage, ObjectStorageSettings
from testing_agent.models import Base
from testing_agent.models.bug import Bug
from testing_agent.models.project import Project
from testing_agent.models.project_member import ProjectMember
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.stored_file import StoredFile
from testing_agent.models.user import User
from testing_agent.repositories.bug import BugRepository
from testing_agent.schemas.stored_file import FileUploadRequest
from testing_agent.services.bug import BugService
from testing_agent.services.stored_file import StoredFileService, utcnow


@compiles(LONGTEXT, "sqlite")
def longtext_sqlite(type_, compiler, **kwargs):
    return "TEXT"


@pytest_asyncio.fixture
async def files():
    with mock_aws():
        settings = ObjectStorageSettings(
            enabled=True, bucket="mtx-test", access_key="test", secret_key="test"
        )
        storage = ObjectStorage(settings)
        storage.client.create_bucket(Bucket=settings.bucket)
        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            session.add_all(
                [
                    User(user_id="owner", nickname="owner"),
                    User(user_id="viewer", nickname="viewer"),
                    User(user_id="member", nickname="member"),
                    Project(project_id="p", user_id="owner", name="p"),
                    Project(project_id="q", user_id="owner", name="q"),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    ProjectMember(project_id="p", user_id="viewer", role="viewer"),
                    ProjectMember(project_id="p", user_id="member", role="member"),
                    Sprint(
                        sprint_id="s",
                        project_id="p",
                        name="s",
                        start_time=utcnow(),
                        end_time=utcnow() + timedelta(days=1),
                    ),
                    Requirement(requirement_id="r", sprint_id="s", name="existing"),
                    Bug(bug_id="bug-1", project_id="p", bug_no=2, title="bug", found_sprint_id="s"),
                ]
            )
            await session.commit()
            yield StoredFileService(session, settings, storage)
        await engine.dispose()


async def upload(files, content=b"hello", filename="a.txt", purpose="requirement"):
    ticket = await files.initiate(
        "owner",
        FileUploadRequest(
            project_id="p",
            filename=filename,
            size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            purpose=purpose,
        ),
    )
    row = await files.get(ticket["fileId"])
    files.storage.client.put_object(Bucket=row.bucket, Key=row.staging_key, Body=content)
    return row, ticket


@pytest.mark.asyncio
async def test_upload_verify_attach_and_replay_cannot_change_file(files):
    row, ticket = await upload(files)
    assert ticket["upload"]["url"]
    await files.complete("owner", row.file_id)
    await files.attach("owner", row.file_id, "p", "requirement", "r", purpose="requirement")
    await files.session.commit()
    # Replay a valid staging authorization after completion.
    files.storage.client.put_object(Bucket=row.bucket, Key=row.staging_key, Body=b"changed")
    await files.complete("owner", row.file_id)
    obj = files.storage.client.get_object(Bucket=row.bucket, Key=row.object_key)
    assert obj["Body"].read() == b"hello"
    assert (await files.download("viewer", row.file_id))["sha256"] == hashlib.sha256(
        b"hello"
    ).hexdigest()


@pytest.mark.asyncio
async def test_permissions_and_invalid_association(files):
    body = FileUploadRequest(project_id="p", filename="a.txt", size=1, sha256="a" * 64)
    for user in ["viewer", "stranger"]:
        with pytest.raises(AppError) as error:
            await files.initiate(user, body)
        assert error.value.http_code == 403
    row, _ = await upload(files)
    with pytest.raises(AppError):
        await files.attach("owner", row.file_id, "p", "requirement", "r", purpose="requirement")
    await files.complete("owner", row.file_id)
    with pytest.raises(AppError):
        await files.download("member", row.file_id)
    with pytest.raises(AppError):
        await files.attach("owner", row.file_id, "q", "requirement", "r", purpose="requirement")
    with pytest.raises(AppError):
        await files.attach("member", row.file_id, "p", "requirement", "r", purpose="requirement")


@pytest.mark.asyncio
async def test_developer_downloads_only_attached_bug_files(files):
    files.session.add(User(user_id="developer", nickname="developer"))
    await files.session.flush()
    files.session.add(ProjectMember(project_id="p", user_id="developer", role="developer"))
    await files.session.commit()
    bug_file, _ = await upload(files, purpose="attachment")
    await files.complete("owner", bug_file.file_id)
    with pytest.raises(AppError) as denied:
        await files.download("developer", bug_file.file_id)
    assert denied.value.http_code == 403
    await files.attach("owner", bug_file.file_id, "p", "bug", "bug-1", purpose="attachment")
    await files.session.commit()
    assert (await files.download("developer", bug_file.file_id))["filename"] == "a.txt"
    requirement_file, _ = await upload(files)
    await files.complete("owner", requirement_file.file_id)
    await files.attach(
        "owner", requirement_file.file_id, "p", "requirement", "r", purpose="requirement"
    )
    await files.session.commit()
    with pytest.raises(AppError) as denied:
        await files.download("developer", requirement_file.file_id)
    assert denied.value.http_code == 403
    body = FileUploadRequest(project_id="p", filename="a.txt", size=1, sha256="a" * 64)
    with pytest.raises(AppError) as denied:
        await files.initiate("developer", body)
    assert denied.value.http_code == 403
    await files.session.delete(
        await files.session.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == "p", ProjectMember.user_id == "developer"
            )
        )
    )
    await files.session.commit()
    with pytest.raises(AppError) as denied:
        await files.download("developer", bug_file.file_id)
    assert denied.value.http_code == 403


@pytest.mark.asyncio
async def test_bad_checksum_and_missing_object_never_ready(files):
    row, _ = await upload(files)
    files.storage.client.put_object(Bucket=row.bucket, Key=row.staging_key, Body=b"xxxxx")
    with pytest.raises(AppError, match="校验失败"):
        await files.complete("owner", row.file_id)
    assert row.status == "pending"
    files.storage.delete(row.staging_key)
    with pytest.raises(AppError, match="尚未上传"):
        await files.complete("owner", row.file_id)
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_cleanup_retains_attached_history_and_expires_temporary(files):
    row, _ = await upload(files)
    await files.complete("owner", row.file_id)
    await files.attach("owner", row.file_id, "p", "requirement", "r", purpose="requirement")
    row.expires_at = utcnow() - timedelta(hours=1)
    await files.session.commit()
    temporary, _ = await upload(files, b"old")
    temp_id = temporary.file_id
    temporary.expires_at = utcnow() - timedelta(hours=1)
    await files.session.commit()
    result = await files.cleanup()
    assert result == {"deleted": 1, "failed": 0}
    assert (
        await files.session.scalar(select(StoredFile).where(StoredFile.file_id == temp_id)) is None
    )
    assert (await files.get(row.file_id)).status == "attached"
    assert (
        files.storage.client.get_object(Bucket=row.bucket, Key=row.object_key)["Body"].read()
        == b"hello"
    )


@pytest.mark.asyncio
async def test_expired_upload_and_type_mismatch(files):
    row, _ = await upload(files)
    row.expires_at = utcnow() - timedelta(hours=1)
    await files.session.commit()
    with pytest.raises(AppError, match="过期"):
        await files.complete("owner", row.file_id)
    bad, _ = await upload(files, b"not a word document", "a.docx")
    with pytest.raises(AppError, match="扩展名"):
        await files.complete("owner", bad.file_id)


@pytest.mark.asyncio
async def test_requirement_api_binds_verified_file_and_negotiates_download(files):
    from types import SimpleNamespace

    import httpx

    from testing_agent.api.deps import get_current_user_id, get_requirement_service
    from testing_agent.app import create_app
    from testing_agent.repositories.requirement import RequirementRepository
    from testing_agent.services.requirement import RequirementService

    class Sprints:
        async def get_accessible_entity(self, *args, **kwargs):
            return SimpleNamespace(project_id="p")

    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "owner"
    app.dependency_overrides[get_requirement_service] = lambda: RequirementService(
        RequirementRepository(files.session), Sprints(), files=files
    )
    row, _ = await upload(files)
    await files.complete("owner", row.file_id)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/sprints/s/requirements",
            json={"name": "Requirement", "documentType": "text", "documentFileId": row.file_id},
        )
        assert response.status_code == 200, response.text
        payload = response.json()["data"]
        assert payload["documentFileId"] == row.file_id
        response = await client.get(
            payload["documentDownloadUrl"], headers={"Accept": "application/json"}
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["sha256"] == row.sha256
        assert "X-Amz-Signature=" in response.json()["url"]
        # Replacing the document keeps old associated objects available for history.
        newer, _ = await upload(files, b"new content")
        await files.complete("owner", newer.file_id)
        response = await client.patch(
            "/v1/requirements/" + payload["requirementId"], json={"documentFileId": newer.file_id}
        )
        assert response.status_code == 200, response.text
        assert (await files.get(row.file_id)).status == "attached"


@pytest.mark.asyncio
async def test_word_object_keeps_original_filename_and_download_metadata(files):
    from io import BytesIO
    from urllib.parse import quote
    from zipfile import ZipFile

    data = BytesIO()
    with ZipFile(data, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
    content = data.getvalue()
    filename = "需求说明 v1.docx"
    row, _ = await upload(files, content, filename)
    await files.complete("owner", row.file_id)
    assert row.object_key.endswith("/" + filename)
    obj = files.storage.client.get_object(Bucket=row.bucket, Key=row.object_key)
    assert obj["Body"].read() == content
    assert (
        obj["ContentType"]
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "filename*=UTF-8''" + quote(filename, safe="") in obj["ContentDisposition"]


@pytest.mark.asyncio
async def test_repair_legacy_names_preserves_bytes_id_and_old_object(files):
    from testing_agent.services.file_naming import repair_file_names

    row, _ = await upload(files)
    row.object_key = row.object_key.rsplit("/", 1)[0] + "/content"
    await files.session.commit()
    await files.complete("owner", row.file_id)
    old_key, file_id = row.object_key, row.file_id
    assert (await repair_file_names(files))[0]["status"] == "eligible"
    assert row.object_key == old_key
    assert (await repair_file_names(files, apply=True))[0]["status"] == "repaired"
    assert row.file_id == file_id
    assert row.object_key.endswith("/a.txt")
    for key in (old_key, row.object_key):
        assert (
            files.storage.client.get_object(Bucket=row.bucket, Key=key)["Body"].read() == b"hello"
        )
    assert await repair_file_names(files, apply=True) == []


@pytest.mark.asyncio
async def test_source_archive_completion_validates_zip_before_attachment(files):
    from io import BytesIO
    from zipfile import ZipFile

    for entries in ([("../escape.js", b"x")], [("a.js", b"x"), ("a.js", b"y")]):
        buffer = BytesIO()
        with ZipFile(buffer, "w") as archive:
            for name, content in entries:
                archive.writestr(name, content)
        row, _ = await upload(files, buffer.getvalue(), "source.zip", "ui_source_archive")
        with pytest.raises(AppError):
            await files.complete("owner", row.file_id)
        assert row.status == "pending"
        with pytest.raises(AppError):
            await files.attach(
                "owner", row.file_id, "p", "ui_source_archive", "task", purpose="ui_source_archive"
            )
        await files.session.rollback()


@pytest.mark.asyncio
async def test_source_archive_s3_binding_replacement_and_transaction_rollback(files, monkeypatch):
    from io import BytesIO
    from zipfile import ZipFile

    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.repositories.ai_generate_task_source_archive import (
        AiGenerateTaskSourceArchiveRepository,
    )
    from testing_agent.services.ai_source_archive import SourceArchiveManager

    task = AiGenerateTask(
        task_id="task",
        task_type="ui_case_generate",
        name="UI",
        project_id="p",
        sprint_id="s",
        requirement_id="r",
        creator_user_id="owner",
        source_type="source_archive",
        source_content="",
    )
    files.session.add(task)
    await files.session.commit()

    async def owned(user, task_id, kind, *, action):
        return await files.session.scalar(
            select(AiGenerateTask).where(AiGenerateTask.task_id == task_id)
        )

    repo = AiGenerateTaskSourceArchiveRepository(files.session)
    manager = SourceArchiveManager(source_archive_repository=repo, files=files, owned_task=owned)
    identifiers = []
    for version in (b"v1", b"v2"):
        buffer = BytesIO()
        with ZipFile(buffer, "w") as archive:
            archive.writestr("src/index.ts", version)
        row, _ = await upload(files, buffer.getvalue(), "source.zip", "ui_source_archive")
        await files.complete("owner", row.file_id)
        identifiers.append(row.file_id)
        result = await manager.upload_source_archive("task", row.file_id, "owner")
        assert result["sourceArchive"]["fileId"] == row.file_id
        assert (await repo.get_source_archive("task")).storage_path == ""
    for identifier in identifiers:
        row = await files.get(identifier)
        assert row.status == "attached"
        assert (await files.ticket(row))["url"]
        assert (
            files.storage.client.get_object(Bucket=row.bucket, Key=row.object_key)["ContentLength"]
            == row.size
        )

    # A file uploaded for another purpose cannot replace the current archive.
    wrong, _ = await upload(files)
    await files.complete("owner", wrong.file_id)
    with pytest.raises(AppError):
        await manager.upload_source_archive("task", wrong.file_id, "owner")
    assert (await repo.get_source_archive("task")).file_id == identifiers[-1]

    # A failed business commit rolls back both file binding and the archive pointer.
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("src/index.ts", b"v3")
    pending, _ = await upload(files, buffer.getvalue(), "source.zip", "ui_source_archive")
    await files.complete("owner", pending.file_id)
    pending_id = pending.file_id

    async def fail_commit():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(repo, "commit", fail_commit)
    with pytest.raises(RuntimeError):
        await manager.upload_source_archive("task", pending_id, "owner")
    assert (await repo.get_source_archive("task")).file_id == identifiers[-1]
    assert (await files.get(pending_id)).status == "ready"


@pytest.mark.asyncio
async def test_ui_source_upload_restricts_extension_size_and_project_role(files):
    for filename, size, user in [
        ("source.txt", 10, "owner"),
        ("source.zip", 104857601, "owner"),
        ("source.zip", 10, "viewer"),
    ]:
        with pytest.raises(AppError):
            await files.initiate(
                user,
                FileUploadRequest(
                    project_id="p",
                    filename=filename,
                    size=size,
                    sha256="0" * 64,
                    purpose="ui_source_archive",
                ),
            )


@pytest.mark.asyncio
async def test_worker_artifact_gateway_binds_only_authorized_execution(files, monkeypatch):
    from types import SimpleNamespace

    from testing_agent.handlers import worker_files
    from testing_agent.models.ui_test_case import UiTestCase
    from testing_agent.models.ui_test_case_run import UiTestCaseRun
    from testing_agent.models.ui_test_suite import UiTestSuite
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.schemas.workers import WorkerTaskEventRequest
    from testing_agent.services.worker_task import WorkerTaskService

    files.session.add_all(
        [
            UiTestSuite(suite_id="suite", requirement_id="r", name="suite"),
            UiTestCase(case_id="case", suite_id="suite", name="case", steps_json=[]),
            UiTestCaseRun(run_id="run", case_id="case", suite_id="suite", trigger_user_id="owner"),
            WorkerTask(domain="ui", task_id="task", task_type="case_debug", run_id="run"),
        ]
    )
    await files.session.commit()

    async def authority(*args):
        return SimpleNamespace(actor="owner", project_id="p")

    monkeypatch.setattr(worker_files, "authority", authority)
    response = await worker_files.initiate_artifact(
        "task",
        worker_files.WorkerFileRequest(
            workerId="w",
            filename="screenshot.png",
            size=8,
            sha256=hashlib.sha256(b"\x89PNG\r\n\x1a\n").hexdigest(),
        ),
        service=None,
        files=files,
    )
    import json

    ticket = json.loads(response.body)
    row = await files.get(ticket["fileId"])
    files.storage.client.put_object(
        Bucket=row.bucket, Key=row.staging_key, Body=b"\x89PNG\r\n\x1a\n"
    )
    body = worker_files.WorkerFileCompleteRequest(workerId="w")
    with pytest.raises(AppError):
        await worker_files.complete_artifact(
            "foreign-task", row.file_id, body, service=None, files=files
        )
    result = await worker_files.complete_artifact(
        "task", row.file_id, body, service=None, files=files
    )
    assert result["path"] == f"/v1/files/{row.file_id}/download"
    assert (await files.download("viewer", row.file_id))["size"] == 8
    service = WorkerTaskService(SimpleNamespace(session=files.session))
    event = WorkerTaskEventRequest(
        workerId="w", tracePath=result["path"], stepResults=[{"screenshotPath": result["path"]}]
    )
    await service.validate_ui_artifacts("task", event)
    with pytest.raises(AppError):
        await service.validate_ui_artifacts("foreign-task", event)
    with pytest.raises(AppError):
        await service.validate_ui_artifacts(
            "task", WorkerTaskEventRequest(workerId="w", tracePath="/tmp/trace.zip")
        )


@pytest.mark.asyncio
async def test_project_skill_file_is_verified_bound_and_downloaded_privately(files):
    from testing_agent.repositories.project_skill_space import ProjectSkillSpaceRepository
    from testing_agent.schemas.project_skill_space import ProjectSkillUploadRequest
    from testing_agent.services.project_skill_space import ProjectSkillSpaceService

    row, _ = await upload(files, b"# test", "SKILL.md", "project_skill")
    await files.complete("owner", row.file_id)
    service = ProjectSkillSpaceService(ProjectSkillSpaceRepository(files.session), files)
    body = ProjectSkillUploadRequest(
        name="test", files=[{"path": "SKILL.md", "fileId": row.file_id}]
    )
    result = await service.upload("p", body, "owner")
    assert result["fileCount"] == 1
    assert (await files.download("viewer", row.file_id))["size"] == 6


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "purpose,filename,folder",
    [
        ("requirement", "需求.txt", "requirements"),
        ("attachment", "图片.png", "attachments"),
        ("ui_source_archive", "源码.zip", "source-archives"),
        ("project_skill", "SKILL.md", "skills"),
        ("ui_artifact", "trace.zip", "ui-artifacts"),
    ],
)
async def test_upload_ticket_uses_business_folder(files, purpose, filename, folder):
    row, ticket = await upload(files, filename=filename, purpose=purpose)
    prefix = (
        f"mtx/_temporary/skills/p/{row.file_id}"
        if purpose == "project_skill"
        else f"mtx/p/{folder}/{row.file_id}"
    )
    assert row.object_key == f"{prefix}/{filename}"
    assert row.staging_key == f"{prefix}/upload"
    assert ticket["upload"]["fields"]["key"] == row.staging_key


@pytest.mark.asyncio
async def test_legacy_object_key_remains_downloadable(files):
    row, _ = await upload(files)
    await files.complete("owner", row.file_id)
    legacy_key = f"mtx/p/{row.file_id}/{row.filename}"
    files.storage.client.copy_object(
        Bucket=row.bucket,
        Key=legacy_key,
        CopySource={"Bucket": row.bucket, "Key": row.object_key},
    )
    files.storage.delete(row.object_key)
    row.object_key = legacy_key
    await files.session.commit()
    ticket = await files.download("owner", row.file_id)
    assert legacy_key in ticket["url"]
    assert (
        files.storage.client.get_object(Bucket=row.bucket, Key=legacy_key)["Body"].read()
        == b"hello"
    )


@pytest.mark.asyncio
async def test_removed_bug_image_remains_readable_from_history_after_cleanup(files):
    content = b"\x89PNG\r\n\x1a\nimage"
    row, _ = await upload(files, content, "evidence.png", "attachment")
    await files.complete("owner", row.file_id)
    original = f'<p>原始问题</p><img data-file-id="{row.file_id}">'
    files.session.add(
        Bug(
            bug_id="bug",
            project_id="p",
            bug_no=1,
            title="bug",
            found_sprint_id="s",
            description_html=original,
        )
    )
    await files.attach("owner", row.file_id, "p", "bug", "bug", purpose="attachment")
    await files.session.commit()
    bugs = BugService(BugRepository(files.session), files)
    await bugs.update("member", "bug", {"description_html": "<p>已修复</p>"})
    result = await bugs.update("member", "bug", {"removed_attachment_file_ids": [row.file_id]})
    assert result["attachments"] == []
    # The full old HTML is retained and its stable file ID must still resolve.
    history = await bugs.repository.list_activities("bug")
    assert history[0].detail_json["changes"][0]["from"] == original
    assert (await files.download("viewer", row.file_id))["sha256"] == row.sha256
    row.expires_at = utcnow() - timedelta(days=1)
    await files.session.commit()
    await files.cleanup()
    assert (await files.download("viewer", row.file_id))["sha256"] == row.sha256
    assert (
        files.storage.client.get_object(Bucket=row.bucket, Key=row.object_key)["Body"].read()
        == content
    )
    # Another authorized editor can restore the archived image without re-uploading it.
    restored = await bugs.update("member", "bug", {"description_html": original})
    assert [item["fileId"] for item in restored["attachments"]] == [row.file_id]


@pytest.mark.asyncio
async def test_cleanup_protects_legacy_deleting_bug_evidence(files):
    row, _ = await upload(files, purpose="attachment")
    await files.complete("owner", row.file_id)
    files.session.add(Bug(bug_id="bug", project_id="p", bug_no=1, title="bug", found_sprint_id="s"))
    await files.attach("owner", row.file_id, "p", "bug", "bug", purpose="attachment")
    row.status = "deleting"
    row.expires_at = utcnow() - timedelta(days=1)
    await files.session.commit()
    await files.cleanup()
    assert (await files.download("viewer", row.file_id))["filename"] == "a.txt"
