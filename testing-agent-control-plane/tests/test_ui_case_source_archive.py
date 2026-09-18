import hashlib
import io
import stat
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from authorization_database import AuthorizationDatabase
from fastapi.testclient import TestClient

from testing_agent.api.deps import (
    get_ai_generate_task_service,
    get_current_user_id,
    get_settings,
    get_worker_task_service,
)
from testing_agent.app import create_app
from testing_agent.core.config import Settings
from testing_agent.models.ai_generate_task import (
    AiGenerateTask,
    AiGenerateTaskRun,
)
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services import ai_generate_task as ai_tasks
from testing_agent.services.ai_generate_task import AiGenerateTaskService
from testing_agent.services.worker_task import WorkerTaskService


def test_ui_case_generate_source_archive_routes_are_public():
    paths = create_app().openapi()["paths"]

    assert "post" in paths["/v1/projects/{projectId}/ui-case-generate-tasks"]
    assert "get" in paths["/v1/projects/{projectId}/ui-case-generate-tasks"]
    assert "get" in paths["/v1/ui-case-generate-tasks/{taskId}"]
    assert "patch" in paths["/v1/ui-case-generate-tasks/{taskId}"]
    assert "delete" in paths["/v1/ui-case-generate-tasks/{taskId}"]
    assert "put" in paths["/v1/ui-case-generate-tasks/{taskId}/source-archive"]
    assert "post" in paths["/v1/ui-case-generate-tasks/{taskId}/run"]
    assert "get" in paths["/v1/ui-case-generate-tasks/{taskId}/runs"]
    assert "get" in paths["/v1/ui-case-generate-task-runs/{runId}"]
    assert "patch" in paths["/v1/ui-case-generate-task-runs/{runId}/result"]
    assert "post" in paths["/v1/ui-case-generate-task-runs/{runId}/review"]
    assert "get" in paths["/internal/ai-worker/tasks/{taskId}/source-archive"]


class UiTaskRepository:
    session = AuthorizationDatabase()

    def __init__(self):
        self.project = SimpleNamespace(project_id="project-1", user_id="user-1")
        self.sprint = SimpleNamespace(sprint_id="sprint-1", project_id="project-1")
        self.requirement = SimpleNamespace(
            requirement_id="requirement-1",
            sprint_id="sprint-1",
            name="Login",
            document_type="text",
            document_content="",
            document_storage_path="",
            document_download_url="",
        )
        self.runs = {}
        self.archive = None
        self.tasks = {}
        self.added = []

    async def get_project(self, project_id):
        return self.project if project_id == self.project.project_id else None

    async def get_sprint(self, sprint_id):
        return self.sprint if sprint_id == self.sprint.sprint_id else None

    async def get_requirement(self, requirement_id):
        return self.requirement if requirement_id == self.requirement.requirement_id else None

    async def get_run(self, run_id):
        return self.runs.get(run_id)

    async def list_runs(self, task_id):
        return [run for run in self.runs.values() if run.task_id == task_id]

    async def get_task(self, task_id):
        return self.tasks.get(task_id)

    async def list_tasks(self, project_id, task_type):
        return [
            task
            for task in self.tasks.values()
            if task.project_id == project_id and task.task_type == task_type
        ]

    def add(self, row):
        self.added.append(row)
        if isinstance(row, AiGenerateTask):
            self.tasks[row.task_id] = row
        elif hasattr(row, "archive_id"):
            self.archive = row
        elif isinstance(row, AiGenerateTaskRun):
            self.runs[row.run_id] = row
            row.error_message = ""
            row.result_yaml = ""
            row.review_status = "pending"
            row.import_status = "pending"
            row.imported_targets = []
            row.imported_at = None
            row.import_migration_complete = True
            row.reviewer_user_id = ""
            row.reviewed_at = None
            row.review_comment = ""
            row.duration_ms = 0

    async def get_source_archive(self, task_id):
        if self.archive is not None and self.archive.task_id == task_id:
            return self.archive
        return None

    async def get_source_archive_for_update(self, task_id):
        return await self.get_source_archive(task_id)

    def add_all(self, rows):
        for row in rows:
            self.add(row)

    async def commit(self):
        return None

    async def refresh(self, _row):
        return None


def ui_task_client(repository, storage_root=None):
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    service = AiGenerateTaskService(repository, source_archive_storage_root=storage_root)
    app.dependency_overrides[get_ai_generate_task_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False), service


def test_ui_task_requires_owned_requirement_and_forces_archive_source():
    repository = UiTaskRepository()
    client, _ = ui_task_client(repository)

    missing_requirement = client.post(
        "/v1/projects/project-1/ui-case-generate-tasks",
        json={"name": "UI generation"},
    )
    created = client.post(
        "/v1/projects/project-1/ui-case-generate-tasks",
        json={
            "name": "UI generation",
            "sprintId": "sprint-1",
            "requirementId": "requirement-1",
            "sourceType": "manual",
            "sourceContent": "must not be exposed",
            "instruction": "Generate login coverage",
        },
    )

    assert missing_requirement.status_code == 400
    assert created.status_code == 200
    assert created.json()["data"] == {
        "taskId": created.json()["data"]["taskId"],
        "taskType": "ui_case_generate",
        "name": "UI generation",
        "projectId": "project-1",
        "sprintId": "sprint-1",
        "requirementId": "requirement-1",
        "creatorUserId": "user-1",
        "sourceType": "source_archive",
        "sourceContent": "",
        "sourceArchive": None,
        "instruction": "Generate login coverage",
        "createdAt": None,
        "updatedAt": None,
    }


def zip_bytes(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return buffer.getvalue()


def test_valid_archive_is_saved_verbatim_and_invalid_replacement_is_atomic(tmp_path):
    repository = UiTaskRepository()
    client, _ = ui_task_client(repository, tmp_path)
    created = client.post(
        "/v1/projects/project-1/ui-case-generate-tasks",
        json={"requirementId": "requirement-1"},
    )
    task_id = created.json()["data"]["taskId"]
    source = zip_bytes([("src/main.py", b"print('ok')\n")])

    uploaded = client.put(
        f"/v1/ui-case-generate-tasks/{task_id}/source-archive",
        files={"file": ("source.zip", source, "application/zip")},
    )

    assert uploaded.status_code == 200
    metadata = uploaded.json()["data"]["sourceArchive"]
    assert metadata["archiveId"]
    assert metadata["filename"] == "source.zip"
    assert metadata["sizeBytes"] == len(source)
    assert metadata["sha256"] == hashlib.sha256(source).hexdigest()
    assert metadata["uploadedAt"]
    assert set(metadata) == {"archiveId", "filename", "sizeBytes", "sha256", "uploadedAt"}
    assert uploaded.json()["data"]["sourceContent"] == ""
    assert Path(repository.archive.storage_path).read_bytes() == source
    updated = client.patch(
        f"/v1/ui-case-generate-tasks/{task_id}",
        json={"sourceType": "manual", "sourceContent": "hidden", "instruction": "updated"},
    )
    assert updated.json()["data"]["sourceType"] == "source_archive"
    assert updated.json()["data"]["sourceContent"] == ""
    assert updated.json()["data"]["sourceArchive"] == metadata

    rejected = client.put(
        f"/v1/ui-case-generate-tasks/{task_id}/source-archive",
        files={"file": ("replacement.zip", zip_bytes([("../escape.py", b"x")]), "application/zip")},
    )
    detail = client.get(f"/v1/ui-case-generate-tasks/{task_id}")

    assert rejected.status_code == 400
    assert detail.status_code == 200
    assert detail.json()["data"]["sourceArchive"] == metadata
    assert Path(repository.archive.storage_path).read_bytes() == source


def zip_with_symlink():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        link = zipfile.ZipInfo("src/link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "main.py")
    return buffer.getvalue()


def create_ui_task(client):
    response = client.post(
        "/v1/projects/project-1/ui-case-generate-tasks",
        json={"requirementId": "requirement-1"},
    )
    assert response.status_code == 200
    return response.json()["data"]["taskId"]


def upload_archive(client, task_id, filename, content):
    return client.put(
        f"/v1/ui-case-generate-tasks/{task_id}/source-archive",
        files={"file": (filename, content, "application/zip")},
    )


def test_archive_rejects_format_and_capacity_limits(tmp_path, monkeypatch):
    repository = UiTaskRepository()
    client, _ = ui_task_client(repository, tmp_path)
    task_id = create_ui_task(client)

    not_zip = upload_archive(client, task_id, "source.tar", b"not a zip")
    corrupt_zip = upload_archive(client, task_id, "source.zip", b"not a zip")
    corrupt_member = bytearray(zip_bytes([("bad.txt", b"healthy")]))
    corrupt_member[corrupt_member.index(b"healthy")] ^= 1
    corrupt_member_zip = upload_archive(client, task_id, "source.zip", corrupt_member)

    compressed = zip_bytes([("a.txt", b"a")])
    monkeypatch.setattr(ai_tasks, "MAX_SOURCE_ARCHIVE_BYTES", len(compressed) - 1)
    too_large = upload_archive(client, task_id, "source.zip", compressed)
    monkeypatch.setattr(ai_tasks, "MAX_SOURCE_ARCHIVE_BYTES", 100 * 1024 * 1024)

    monkeypatch.setattr(ai_tasks, "MAX_SOURCE_ARCHIVE_UNCOMPRESSED_BYTES", 1)
    expanded_too_large = upload_archive(
        client, task_id, "source.zip", zip_bytes([("a.txt", b"ab")])
    )
    monkeypatch.setattr(ai_tasks, "MAX_SOURCE_ARCHIVE_UNCOMPRESSED_BYTES", 1024 * 1024 * 1024)

    monkeypatch.setattr(ai_tasks, "MAX_SOURCE_ARCHIVE_FILES", 1)
    too_many_files = upload_archive(
        client,
        task_id,
        "source.zip",
        zip_bytes([("a.txt", b""), ("b.txt", b"")]),
    )

    assert [
        response.status_code
        for response in (
            not_zip,
            corrupt_zip,
            corrupt_member_zip,
            too_large,
            expanded_too_large,
            too_many_files,
        )
    ] == [400, 400, 400, 400, 400, 400]
    assert repository.archive is None


@pytest.mark.parametrize(
    "source",
    [
        zip_bytes([("/absolute.py", b"x")]),
        zip_bytes([("C:/absolute.py", b"x")]),
        zip_bytes([("../escape.py", b"x")]),
        zip_bytes([("src/main.py", b"x"), ("src/./main.py", b"y")]),
        zip_with_symlink(),
    ],
)
def test_archive_rejects_unsafe_and_duplicate_entries(tmp_path, source):
    repository = UiTaskRepository()
    client, _ = ui_task_client(repository, tmp_path)
    task_id = create_ui_task(client)

    response = upload_archive(client, task_id, "source.zip", source)

    assert response.status_code == 400
    assert repository.archive is None


def test_ui_run_requires_archive_and_snapshot_uses_worker_current_source_urls(tmp_path):
    repository = UiTaskRepository()
    client, _ = ui_task_client(repository, tmp_path)
    task_id = create_ui_task(client)

    missing_archive = client.post(
        f"/v1/ui-case-generate-tasks/{task_id}/run",
        json={"connectionId": "llm-1"},
    )
    assert missing_archive.status_code == 400

    source = zip_bytes([("src/main.py", b"v1")])
    assert upload_archive(client, task_id, "source.zip", source).status_code == 200

    started = client.post(
        f"/v1/ui-case-generate-tasks/{task_id}/run",
        json={"connectionId": "llm-1"},
    )

    assert started.status_code == 200
    worker_task = next(row for row in repository.added if isinstance(row, WorkerTask))
    snapshot = started.json()["data"]["snapshotJson"]
    assert snapshot["sourceType"] == "source_archive"
    assert snapshot["sourceContent"] == ""
    assert snapshot["sourceArchiveDownloadUrl"] == (
        f"/internal/ai-worker/tasks/{worker_task.task_id}/source-archive"
    )
    assert "documentDownloadUrl" not in snapshot


def test_ui_run_snapshot_includes_imported_requirement_enhanced_text(tmp_path):
    repository = UiTaskRepository()
    repository.requirement.document_content = "已确认的登录需求"
    client, _ = ui_task_client(repository, tmp_path)
    task_id = create_ui_task(client)
    uploaded = upload_archive(client, task_id, "source.zip", zip_bytes([("src/main.py", b"v1")]))
    assert uploaded.status_code == 200

    started = client.post(
        f"/v1/ui-case-generate-tasks/{task_id}/run",
        json={"connectionId": "llm-1"},
    )

    assert started.status_code == 200
    snapshot = started.json()["data"]["snapshotJson"]
    assert snapshot["sourceContent"] == "已确认的登录需求"
    assert "documentDownloadUrl" not in snapshot


def worker_settings(upload_dir):
    return Settings(
        env="test",
        http_host="127.0.0.1",
        http_port=8000,
        jwt_key="test",
        jwt_expire_hours=1,
        integration_key="integration",
        worker_key="worker-token",
        database_url="",
        uploads_dir=str(upload_dir),
    )


class WorkerAssetRepository:
    def __init__(self, worker_task, run, source_repository, requirement):
        self.worker_task = worker_task
        self.run = run
        self.source_repository = source_repository
        self.requirement = requirement
        self.session = None

    async def get_worker_task(self, domain, task_id):
        if domain == "ai" and task_id == self.worker_task.task_id:
            return self.worker_task
        return None

    async def get_ai_run(self, run_id):
        return self.run if run_id == self.run.run_id else None

    async def get_source_archive(self, task_id):
        return await self.source_repository.get_source_archive(task_id)

    async def get_requirement(self, requirement_id):
        if requirement_id == self.requirement.requirement_id:
            return self.requirement
        return None


def test_worker_downloads_latest_archive_and_current_optional_requirement_document(
    tmp_path, monkeypatch
):
    from unittest.mock import AsyncMock

    from testing_agent.services import worker_task as worker_module

    # File delivery contract uses a fake queue; real dispatch authorization is tested at HTTP/DB.
    monkeypatch.setattr(worker_module, "authorize_execution", AsyncMock())
    repository = UiTaskRepository()
    user_client, _ = ui_task_client(repository, tmp_path)
    task_id = create_ui_task(user_client)
    first = zip_bytes([("version.txt", b"v1")])
    second = zip_bytes([("version.txt", b"v2")])
    assert upload_archive(user_client, task_id, "v1.zip", first).status_code == 200
    started = user_client.post(
        f"/v1/ui-case-generate-tasks/{task_id}/run",
        json={"connectionId": "llm-1"},
    )
    assert started.status_code == 200
    run = repository.runs[started.json()["data"]["runId"]]
    worker_task = next(row for row in repository.added if isinstance(row, WorkerTask))

    assert upload_archive(user_client, task_id, "v2.zip", second).status_code == 200
    document_path = tmp_path / "current-requirement.txt"
    document_path.write_bytes(b"current requirement")
    repository.requirement.document_storage_path = str(document_path)
    repository.requirement.document_filename = "current-requirement.txt"

    settings = worker_settings(tmp_path)
    worker_repository = WorkerAssetRepository(worker_task, run, repository, repository.requirement)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_worker_task_service] = lambda: WorkerTaskService(worker_repository)
    worker_client = TestClient(app, raise_server_exceptions=False)
    headers = {"X-Worker-Token": "worker-token"}
    unauthorized_archive = worker_client.get(
        f"/internal/ai-worker/tasks/{worker_task.task_id}/source-archive"
    )
    unauthorized_document = worker_client.get(
        f"/internal/ai-worker/tasks/{worker_task.task_id}/requirement-document"
    )

    archive_response = worker_client.get(
        f"/internal/ai-worker/tasks/{worker_task.task_id}/source-archive",
        headers=headers,
    )
    document_response = worker_client.get(
        f"/internal/ai-worker/tasks/{worker_task.task_id}/requirement-document",
        headers=headers,
    )

    assert unauthorized_archive.status_code == 401
    assert unauthorized_document.status_code == 401
    assert archive_response.status_code == 200
    assert archive_response.content == second
    assert "v2.zip" in archive_response.headers["content-disposition"]
    assert document_response.status_code == 200
    assert document_response.content == b"current requirement"

    repository.requirement.document_storage_path = ""
    repository.requirement.document_content = "inline current requirement"
    inline_document_response = worker_client.get(
        f"/internal/ai-worker/tasks/{worker_task.task_id}/requirement-document",
        headers=headers,
    )

    assert inline_document_response.status_code == 200
    assert inline_document_response.content == b"inline current requirement"

    run.task_id = "different-generate-task"
    wrong_archive = worker_client.get(
        f"/internal/ai-worker/tasks/{worker_task.task_id}/source-archive",
        headers=headers,
    )
    wrong_document = worker_client.get(
        f"/internal/ai-worker/tasks/{worker_task.task_id}/requirement-document",
        headers=headers,
    )

    assert wrong_archive.status_code == 404
    assert wrong_document.status_code == 404


@pytest.mark.parametrize("root_key", ["cases", "items"])
def test_ui_candidate_can_be_edited_approved_and_then_frozen(tmp_path, root_key):
    repository = UiTaskRepository()
    client, _ = ui_task_client(repository, tmp_path)
    task_id = create_ui_task(client)
    assert (
        upload_archive(client, task_id, "source.zip", zip_bytes([("main.py", b"x")])).status_code
        == 200
    )
    started = client.post(
        f"/v1/ui-case-generate-tasks/{task_id}/run",
        json={"connectionId": "llm-1"},
    )
    run_id = started.json()["data"]["runId"]
    repository.runs[run_id].status = "success"
    candidate = f"""{root_key}:
  - name: Login
    enabled: true
    orderNo: 1
    stepsJson:
      - orderNo: 1
        stepName: Open login
        keyword: open
        operationValue: https://example.test/login
        continueOnFailure: false
        enabled: true
"""

    invalid = client.patch(
        f"/v1/ui-case-generate-task-runs/{run_id}/result",
        json={"resultYaml": "cases:\n  - name: Missing fields\n"},
    )
    saved = client.patch(
        f"/v1/ui-case-generate-task-runs/{run_id}/result",
        json={"resultYaml": candidate},
    )
    approved = client.post(
        f"/v1/ui-case-generate-task-runs/{run_id}/review",
        json={"action": "approve", "reviewComment": "ready"},
    )
    frozen = client.patch(
        f"/v1/ui-case-generate-task-runs/{run_id}/result",
        json={"resultYaml": "cases: []"},
    )

    assert invalid.status_code == 400
    assert saved.status_code == 200
    assert saved.json()["data"]["resultYaml"] == candidate
    assert approved.status_code == 200
    assert approved.json()["data"]["reviewStatus"] == "approved"
    assert approved.json()["data"]["importStatus"] == "pending"
    assert approved.json()["data"]["importedTargets"] == []
    assert frozen.status_code == 400


def test_ui_generation_user_routes_reject_cross_user_access(tmp_path):
    repository = UiTaskRepository()
    client, _ = ui_task_client(repository, tmp_path)
    task_id = create_ui_task(client)
    assert (
        upload_archive(client, task_id, "source.zip", zip_bytes([("main.py", b"x")])).status_code
        == 200
    )
    started = client.post(
        f"/v1/ui-case-generate-tasks/{task_id}/run",
        json={"connectionId": "llm-1"},
    )
    assert started.status_code == 200
    run_id = started.json()["data"]["runId"]

    client.app.dependency_overrides[get_current_user_id] = lambda: "user-2"
    responses = [
        client.post(
            "/v1/projects/project-1/ui-case-generate-tasks",
            json={"requirementId": "requirement-1"},
        ),
        client.get("/v1/projects/project-1/ui-case-generate-tasks"),
        client.get(f"/v1/ui-case-generate-tasks/{task_id}"),
        client.patch(f"/v1/ui-case-generate-tasks/{task_id}", json={"instruction": "foreign"}),
        client.delete(f"/v1/ui-case-generate-tasks/{task_id}"),
        upload_archive(client, task_id, "replacement.zip", zip_bytes([("main.py", b"foreign")])),
        client.post(
            f"/v1/ui-case-generate-tasks/{task_id}/run",
            json={"connectionId": "llm-1"},
        ),
        client.get(f"/v1/ui-case-generate-tasks/{task_id}/runs"),
        client.get(f"/v1/ui-case-generate-task-runs/{run_id}"),
        client.patch(
            f"/v1/ui-case-generate-task-runs/{run_id}/result",
            json={"resultYaml": "cases: []"},
        ),
        client.post(
            f"/v1/ui-case-generate-task-runs/{run_id}/review",
            json={"action": "approve"},
        ),
    ]

    assert [response.status_code for response in responses] == [403] * len(responses)
