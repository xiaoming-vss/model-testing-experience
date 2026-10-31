"""Shared UI task source-archive HTTP helpers; no collected tests."""

import hashlib
import io
import zipfile
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from authorization_database import AuthorizationDatabase
from fastapi.testclient import TestClient

from support.execution_writer import MemoryExecutionWriter
from support.generation import generation_services, install_generation_services
from testing_agent.api.deps import get_current_user_id
from testing_agent.app import create_app
from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
from testing_agent.models.worker_task import WorkerTask


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

    async def list_ui_source_cases(self, requirement_id, case_ids=None):
        cases = [
            {
                "caseId": "formal-1",
                "suiteId": "suite-1",
                "suiteName": "Login",
                "module": "login",
                "title": "登录成功",
                "content": {
                    "preconditions": [],
                    "steps": [{"action": "打开登录页面", "expected": "页面可见"}],
                },
            }
        ]
        return [case for case in cases if case_ids is None or case["caseId"] in case_ids]

    async def get_latest_ai_dispatch(self, run_id):
        workers = [
            row for row in self.added if isinstance(row, WorkerTask) and row.run_id == run_id
        ]
        if not workers:
            return None
        latest = workers[-1]
        return SimpleNamespace(
            task_id=latest.task_id, status=latest.status, llm_connection_id="llm-1"
        )

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

    async def rollback(self):
        return None

    async def refresh(self, _row):
        return None


class FakeFiles:
    def __init__(self):
        self.rows = {}

    async def get(self, file_id):
        from testing_agent.core.errors import ErrNotFound

        if file_id not in self.rows:
            raise ErrNotFound
        return self.rows[file_id]

    async def attach(self, user, file_id, project, resource, resource_id, *, purpose):
        return await self.get(file_id)

    async def ticket(self, row):
        return {
            "url": "https://s3.test/" + row.file_id,
            "filename": row.filename,
            "size": row.size,
            "sha256": row.sha256,
        }


def ui_task_client(repository, storage_root=None):
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    files = FakeFiles()
    service = generation_services(repository, files=files, execution_writer=MemoryExecutionWriter())
    app.state.test_files = files
    install_generation_services(app, service)
    return TestClient(app, raise_server_exceptions=False), service


def zip_bytes(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return buffer.getvalue()


def create_ui_task(client):
    response = client.post(
        "/v1/projects/project-1/ui-case-generate-tasks",
        json={"requirementId": "requirement-1"},
    )
    assert response.status_code == 200
    return response.json()["data"]["taskId"]


def upload_archive(client, task_id, filename, content):
    file_id = str(uuid4())
    client.app.state.test_files.rows[file_id] = SimpleNamespace(
        file_id=file_id,
        filename=filename,
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        completed_at=datetime.now(UTC),
    )
    return client.put(
        f"/v1/ui-case-generate-tasks/{task_id}/source-archive", json={"fileId": file_id}
    )
