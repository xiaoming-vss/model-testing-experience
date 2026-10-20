import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from support.stored_files import files as files
from support.stored_files import upload

from testing_agent.app import create_app
from testing_agent.core.errors import AppError
from testing_agent.repositories.project_skill_space import ProjectSkillSpaceRepository
from testing_agent.schemas.project_skill_space import ProjectSkillUploadRequest
from testing_agent.services.builtin_skills import sync_builtin_skills
from testing_agent.services.project_skill_space import ProjectSkillSpaceService


def service(files):
    return ProjectSkillSpaceService(ProjectSkillSpaceRepository(files.session), files)


async def folder(files, name="custom", entries=None):
    manifest = []
    for path, content in (
        entries or {"SKILL.md": b"# skill", "scripts/run.py": b"print(1)"}
    ).items():
        row, _ = await upload(files, content, path.split("/")[-1], "project_skill")
        await files.complete("owner", row.file_id)
        manifest.append({"path": path, "fileId": row.file_id})
    return ProjectSkillUploadRequest(name=name, files=manifest)


@pytest.mark.asyncio
async def test_folder_replace_removes_old_files_and_keeps_identity(files):
    svc = service(files)
    first = await svc.upload("p", await folder(files), "owner")
    before = await svc.repository.get("p", first["skillSpaceId"])
    old_ids = [entry["fileId"] for entry in before.manifest]
    second = await svc.upload("p", await folder(files, entries={"SKILL.md": b"# new"}), "owner")
    assert second["skillSpaceId"] == first["skillSpaceId"]
    assert second["fileCount"] == 1
    assert "version" not in second
    for file_id in old_ids:
        assert (await files.get(file_id)).status == "deleting"
    filename, content = await svc.download_zip("p", second["skillSpaceId"], "viewer")
    assert filename == "custom.zip"
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert archive.namelist() == ["custom/SKILL.md"]
        assert archive.read("custom/SKILL.md") == b"# new"
    assert (await svc.list("q", "owner"))["items"] == []


@pytest.mark.asyncio
async def test_defaults_global_read_only_and_can_be_overwritten_by_sync(files, tmp_path):
    folder_path = tmp_path / "builtin"
    folder_path.mkdir()
    (folder_path / "SKILL.md").write_text("default")
    (folder_path / "old.txt").write_text("old")
    await sync_builtin_skills(files, tmp_path)
    svc = service(files)
    default = (await svc.list("p", "viewer"))["items"][0]
    assert default["isDefault"] and default["projectId"] is None
    assert (await svc.list("q", "owner"))["items"][0]["skillSpaceId"] == default["skillSpaceId"]
    with pytest.raises(AppError, match="不允许删除"):
        await svc.delete("p", default["skillSpaceId"], "owner")
    with pytest.raises(AppError, match="同名"):
        await svc.upload("p", await folder(files, "builtin"), "owner")
    (folder_path / "old.txt").unlink()
    (folder_path / "SKILL.md").write_text("updated")
    await sync_builtin_skills(files, tmp_path)
    changed = (await svc.list("p", "owner"))["items"][0]
    assert changed["skillSpaceId"] == default["skillSpaceId"]
    assert changed["fileCount"] == 1
    _, data = await svc.download_zip("p", default["skillSpaceId"], "viewer")
    assert zipfile.ZipFile(io.BytesIO(data)).read("builtin/SKILL.md") == b"updated"


@pytest.mark.asyncio
async def test_owner_permissions_and_cross_project_file_binding(files):
    svc = service(files)
    body = await folder(files)
    for user in ["viewer", "member", "stranger"]:
        with pytest.raises(AppError):
            await svc.upload("p", body, user)
    with pytest.raises(AppError):
        await svc.upload("q", body, "owner")
    await files.session.rollback()
    assert (await svc.list("q", "owner"))["items"] == []


@pytest.mark.parametrize(
    "paths",
    [
        ["a.md"],
        ["SKILL.md", "../escape.py"],
        ["SKILL.md", "/abs"],
        ["SKILL.md", "a\\b"],
        ["SKILL.md", "x", "x/y"],
        ["SKILL.md", "skill.md"],
    ],
)
def test_invalid_manifest_rejected(paths):
    with pytest.raises(ValidationError):
        ProjectSkillUploadRequest(
            name="test", files=[{"path": p, "fileId": str(i)} for i, p in enumerate(paths)]
        )


@pytest.mark.asyncio
async def test_failed_file_validation_does_not_replace_existing(files):
    svc = service(files)
    original = await svc.upload("p", await folder(files), "owner")
    body = await folder(files)
    body.files[1].path = "wrong.py"
    with pytest.raises(AppError, match="不一致"):
        await svc.upload("p", body, "owner")
    await files.session.rollback()
    row = await svc.repository.get("p", original["skillSpaceId"])
    assert row.hash == original["hash"]
    assert len(row.manifest) == 2


def test_project_skill_download_requires_login():
    response = TestClient(create_app()).get("/v1/projects/p/skills/s/download")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_worker_skill_files_require_active_owner_and_default_membership(files, tmp_path):
    from datetime import timedelta
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from testing_agent.handlers.worker_skills import skill_file, skill_manifest
    from testing_agent.services.stored_file import utcnow

    source = tmp_path / "builtin"
    source.mkdir()
    (source / "SKILL.md").write_text("system")
    await sync_builtin_skills(files, tmp_path)
    task = SimpleNamespace(
        worker_id="worker", status="running", lease_expires_at=utcnow() + timedelta(minutes=2)
    )
    worker = SimpleNamespace(
        ai_worker_task=AsyncMock(return_value=task),
        repository=SimpleNamespace(session=files.session),
    )
    response = await skill_manifest("task", "builtin", "worker", worker)
    assert response.headers["cache-control"] == "no-store"
    import json

    file_id = json.loads(response.body)["files"][0]["fileId"]
    response = await skill_file("task", "builtin", file_id, "worker", worker, files)
    assert "url" in json.loads(response.body)
    for name, who in [("builtin", "another"), ("custom", "worker")]:
        with pytest.raises(AppError):
            await skill_manifest("task", name, who, worker)
    with pytest.raises(AppError):
        await skill_file("task", "builtin", "foreign-file", "worker", worker, files)
    task.lease_expires_at = utcnow() - timedelta(seconds=1)
    with pytest.raises(AppError):
        await skill_manifest("task", "builtin", "worker", worker)


@pytest.mark.asyncio
async def test_readable_paths_survive_replacement_cleanup(files):
    from datetime import timedelta

    from sqlalchemy import select

    from testing_agent.models.stored_file import StoredFile
    from testing_agent.services.stored_file import utcnow

    svc = service(files)
    first = await svc.upload("p", await folder(files), "owner")
    skill = await svc.repository.get("p", first["skillSpaceId"])
    for entry in skill.manifest:
        row = await files.get(entry["fileId"])
        assert row.object_key == "mtx/skills/projects/p/custom/" + entry["path"]
    await svc.upload("p", await folder(files, entries={"SKILL.md": b"replacement"}), "owner")
    for row in await files.session.scalars(select(StoredFile)):
        row.expires_at = utcnow() - timedelta(seconds=1)
    await files.session.commit()
    assert (await files.cleanup())["failed"] == 0
    objects = files.storage.client.list_objects_v2(Bucket=files.settings.bucket)["Contents"]
    assert [obj["Key"] for obj in objects] == ["mtx/skills/projects/p/custom/SKILL.md"]
    _, data = await svc.download_zip("p", first["skillSpaceId"], "owner")
    assert zipfile.ZipFile(io.BytesIO(data)).read("custom/SKILL.md") == b"replacement"


@pytest.mark.asyncio
async def test_default_paths_and_idempotent_migration(files, tmp_path):
    from sqlalchemy import select

    from testing_agent.models.project_skill_space import ProjectSkillSpace
    from testing_agent.services.skill_storage import migrate_skill_paths

    source = tmp_path / "builtin"
    (source / "scripts").mkdir(parents=True)
    (source / "SKILL.md").write_text("default")
    (source / "scripts" / "run.py").write_text("print(1)")
    await sync_builtin_skills(files, tmp_path)
    skill = await files.session.scalar(select(ProjectSkillSpace))
    for entry in skill.manifest:
        row = await files.get(entry["fileId"])
        assert row.object_key == "mtx/skills/system/builtin/" + entry["path"]
        # Simulate the former ID-based layout without changing file associations.
        old = "legacy/" + row.file_id + "/" + row.filename
        files.storage.client.copy_object(
            Bucket=row.bucket, Key=old, CopySource={"Bucket": row.bucket, "Key": row.object_key}
        )
        files.storage.client.delete_object(Bucket=row.bucket, Key=row.object_key)
        row.object_key = old
    await files.session.commit()
    await migrate_skill_paths(files)
    await migrate_skill_paths(files)
    for entry in skill.manifest:
        row = await files.get(entry["fileId"])
        assert row.object_key == "mtx/skills/system/builtin/" + entry["path"]
        obj = files.storage.client.get_object(Bucket=row.bucket, Key=row.object_key)
        assert len(obj["Body"].read()) == row.size


@pytest.mark.asyncio
async def test_failed_publication_restores_current_contents(files, monkeypatch):
    svc = service(files)
    result = await svc.upload("p", await folder(files), "owner")
    body = await folder(files, entries={"SKILL.md": b"changed", "scripts/run.py": b"changed"})
    original = files.storage.client.copy_object

    def fail_second(**kwargs):
        if kwargs["Key"] == "mtx/skills/projects/p/custom/scripts/run.py":
            # Fail only the new copy, permitting the compensation copy.
            if kwargs["CopySource"]["Key"].endswith("/run.py"):
                raise RuntimeError("copy failure")
        return original(**kwargs)

    monkeypatch.setattr(files.storage.client, "copy_object", fail_second)
    with pytest.raises(RuntimeError, match="copy failure"):
        await svc.upload("p", body, "owner")
    _, data = await svc.download_zip("p", result["skillSpaceId"], "owner")
    archive = zipfile.ZipFile(io.BytesIO(data))
    assert archive.read("custom/SKILL.md") == b"# skill"
    assert archive.read("custom/scripts/run.py") == b"print(1)"


@pytest.mark.asyncio
async def test_existing_file_cannot_be_rebound_to_a_different_path(files):
    svc = service(files)
    result = await svc.upload("p", await folder(files), "owner")
    skill = await svc.repository.get("p", result["skillSpaceId"])
    body = ProjectSkillUploadRequest(
        name="custom",
        files=[
            {
                "path": "other/run.py" if entry["path"] == "scripts/run.py" else entry["path"],
                "fileId": entry["fileId"],
            }
            for entry in skill.manifest
        ],
    )
    with pytest.raises(AppError, match="重新上传"):
        await svc.upload("p", body, "owner")
