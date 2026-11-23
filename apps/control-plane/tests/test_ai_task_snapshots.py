from types import SimpleNamespace

import pytest
from authorization_database import AuthorizationDatabase
from support import generation as ai_tasks
from support.generation import generation_services
from support.remaining_control_plane import (
    TaskScopeFixture,
)

from testing_agent.core.errors import (
    ErrBadRequest,
)
from testing_agent.domain.ai_tasks import task_type_for as _generation_task_type_for
from testing_agent.services import worker
from testing_agent.services.ai_task_output import (
    build_generate_run_snapshot as _generation_build_generate_run_snapshot,
)
from testing_agent.services.integration_connection import IntegrationConnectionService


def test_llm_credentials_payload_uses_stored_connection_secrets():
    connection = SimpleNamespace(
        connection_id="conn-1",
        base_url="https://llm.example",
        access_token="access-token",
        secret_json={"apiKey": "secret-key", "modelId": "gpt-test"},
        extra_json={"organization": "org-1"},
    )

    assert worker.llm_credentials_payload("task-1", connection) == {
        "taskId": "task-1",
        "connectionId": "conn-1",
        "baseUrl": "https://llm.example",
        "modelId": "gpt-test",
        "apiKey": "secret-key",
        "organization": "org-1",
    }


@pytest.mark.asyncio
async def test_update_llm_connection_model_id_replaces_json_payload_for_persistence():
    original_extra = {"modelId": "old-model"}
    connection = SimpleNamespace(
        connection_id="conn-1",
        user_id="user-1",
        provider="llm",
        name="LLM",
        base_url="https://llm.example",
        auth_type="api_key",
        account="",
        secret_json={"apiKey": "key"},
        access_token="key",
        status="active",
        extra_json=original_extra,
        last_auth_at=None,
        last_auth_error="",
        token_expires_at=None,
        created_at=None,
        updated_at=None,
    )

    from unittest.mock import AsyncMock

    class FakeRepository:
        session = SimpleNamespace(scalar=AsyncMock(return_value=None))

        async def get(self, user_id, provider, connection_id, project_id="", *, lock=False):
            assert user_id == "user-1"
            assert provider == "llm"
            assert connection_id == "conn-1"
            return connection

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    service = IntegrationConnectionService(FakeRepository())

    payload = await service.update(
        "llm",
        "conn-1",
        {"modelId": "new-model"},
        "user-1",
    )

    assert payload["modelId"] == "new-model"
    assert connection.extra_json == {"modelId": "new-model"}
    assert connection.extra_json is not original_extra
    assert original_extra == {"modelId": "old-model"}


def test_requirement_analysis_kind_maps_to_requirement_analysis_task_type():
    assert _generation_task_type_for("function") == "functional_case_generate"
    assert _generation_task_type_for("requirement_analysis") == "requirement_analysis"


@pytest.mark.asyncio
async def test_requirement_analysis_create_requires_requirement_id():
    class FakeRepository:
        session = AuthorizationDatabase()

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        def add(self, row):
            raise AssertionError("task should not be created without requirementId")

        async def commit(self):
            raise AssertionError("task should not commit without requirementId")

        async def refresh(self, row):
            raise AssertionError("task should not refresh without requirementId")

    service = generation_services(FakeRepository())

    with pytest.raises(type(ErrBadRequest)):
        await service.commands.create(
            "requirement_analysis",
            "project-1",
            {"name": "Analyze requirement"},
            "user-1",
        )


@pytest.mark.asyncio
async def test_api_generate_run_snapshot_uses_selected_interfaces(monkeypatch):
    from testing_agent.services import ai_task_output

    class FakeRepository:
        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return None

    async def fake_interface_snapshot(repository, task):
        assert task.interface_ids_json == ["interface-1"]
        return (
            [
                {
                    "softwareRepositoryId": "repository-1",
                    "name": "订单服务",
                    "basePath": "/api",
                    "gitRepository": {
                        "instanceUrl": "https://gitlab.example.com",
                        "pathWithNamespace": "commerce/order-service",
                    },
                }
            ],
            [{"interfaceId": "interface-1", "name": "创建订单"}],
        )

    monkeypatch.setattr(ai_task_output, "_api_interface_snapshot", fake_interface_snapshot)
    task = SimpleNamespace(
        task_id="task-1",
        task_type="api_case_generate",
        name="Generate API cases",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="requirement-1",
        source_type="interface_library",
        source_content="",
        interface_ids_json=["interface-1"],
        instruction="cover APIs",
    )

    snapshot = await _generation_build_generate_run_snapshot(FakeRepository(), "api", task, "run-1")

    assert snapshot == {
        "taskId": "task-1",
        "runId": "run-1",
        "taskType": "api_case_generate",
        "name": "Generate API cases",
        "projectId": "project-1",
        "sprintId": "sprint-1",
        "requirementId": "requirement-1",
        "sourceType": "interface_library",
        "instruction": "cover APIs",
        "interfaces": [{"interfaceId": "interface-1", "name": "创建订单"}],
        "softwareRepositories": [
            {
                "softwareRepositoryId": "repository-1",
                "name": "订单服务",
                "basePath": "/api",
                "gitRepository": {
                    "instanceUrl": "https://gitlab.example.com",
                    "pathWithNamespace": "commerce/order-service",
                },
            }
        ],
    }


@pytest.mark.asyncio
async def test_ai_generate_run_uses_go_connection_id_for_worker_task(monkeypatch):
    from unittest.mock import AsyncMock

    from testing_agent.services import (
        ai_run_launcher,
        ai_task_output,
        standalone_execution,
        standalone_execution_view,
    )

    async def fake_interface_snapshot(repository, task):
        return [], []

    monkeypatch.setattr(ai_task_output, "_api_interface_snapshot", fake_interface_snapshot)

    class FakeRepository(TaskScopeFixture):
        def __init__(self):
            self.rows = []

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return SimpleNamespace(
                task_id="task-1",
                task_type="api_case_generate",
                name="Generate API cases",
                project_id="project-1",
                sprint_id="sprint-1",
                requirement_id="",
                creator_user_id="user-1",
                source_type="interface_library",
                source_content="",
                interface_ids_json=[],
                instruction="cover APIs",
            )

        def add_all(self, rows):
            self.rows.extend(rows)

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    ids = iter(["run-1", "worker-task-1"])
    monkeypatch.setattr(ai_tasks, "new_id", lambda: next(ids))
    repository = FakeRepository()
    service = generation_services(repository)
    dispatch = AsyncMock(return_value=(SimpleNamespace(execution_id="run-1"), None, None))
    monkeypatch.setattr(standalone_execution, "start_standalone_execution", dispatch)
    monkeypatch.setattr(standalone_execution_view, "project_standalone_execution", AsyncMock())
    monkeypatch.setattr(ai_run_launcher, "dump_run", lambda projected: {})

    await service.launcher.launch("api", "task-1", {"connectionId": "conn-1"}, "user-1")

    assert dispatch.await_args.kwargs["connection_id"] == "conn-1"
    assert dispatch.await_args.kwargs["execution_id"] == "run-1"
    assert dispatch.await_args.kwargs["request_id"] == "worker-task-1"
    assert repository.rows == []


@pytest.mark.asyncio
async def test_ai_generate_run_requires_go_connection_id():
    class FakeRepository(TaskScopeFixture):
        async def get_task(self, task_id):
            return SimpleNamespace(
                task_id="task-1",
                task_type="api_case_generate",
                name="Generate API cases",
                project_id="project-1",
                sprint_id="sprint-1",
                requirement_id="",
                creator_user_id="user-1",
                source_type="text",
                source_content="api source",
                instruction="cover APIs",
            )

        def add_all(self, rows):
            raise AssertionError("run should reject missing connectionId before creating rows")

        async def commit(self):
            raise AssertionError("run should reject missing connectionId before committing")

    service = generation_services(FakeRepository())

    with pytest.raises(type(ErrBadRequest)):
        await service.launcher.launch("api", "task-1", {}, "user-1")


@pytest.mark.asyncio
async def test_requirement_analysis_snapshot_prefers_document_content_for_docx_with_file():
    class FakeRepository:
        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return SimpleNamespace(
                document_type="docx",
                document_content="reviewed docx requirement content",
                document_storage_path="storage/requirements/requirement-1/requirement.docx",
                document_download_url="/v1/requirements/requirement-1/download",
            )

    task = SimpleNamespace(
        task_id="task-1",
        task_type="requirement_analysis",
        name="Analyze requirement",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="requirement-1",
        source_type="manual",
        source_content="task source should not be used",
        instruction="find ambiguities",
    )

    snapshot = await _generation_build_generate_run_snapshot(
        FakeRepository(), "requirement_analysis", task, "run-1", worker_task_id="worker-task-1"
    )

    assert snapshot["documentType"] == "docx"
    assert snapshot["documentDownloadUrl"] == (
        "/internal/ai-worker/tasks/worker-task-1/requirement-document"
    )
    assert snapshot["sourceContent"] == "reviewed docx requirement content"


@pytest.mark.asyncio
async def test_requirement_analysis_snapshot_uses_docx_download_url_when_document_content_empty():
    class FakeRepository:
        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return SimpleNamespace(
                document_type="docx",
                document_content="",
                document_storage_path="storage/requirements/requirement-1/requirement.docx",
                document_download_url="/v1/requirements/requirement-1/download",
            )

    task = SimpleNamespace(
        task_id="task-1",
        task_type="requirement_analysis",
        name="Analyze requirement",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="requirement-1",
        source_type="manual",
        source_content="task source should not be used",
        instruction="find ambiguities",
    )

    snapshot = await _generation_build_generate_run_snapshot(
        FakeRepository(), "requirement_analysis", task, "run-1", worker_task_id="worker-task-1"
    )

    assert snapshot["documentType"] == "docx"
    assert snapshot["documentDownloadUrl"] == (
        "/internal/ai-worker/tasks/worker-task-1/requirement-document"
    )
    assert snapshot["sourceContent"] == (
        "/internal/ai-worker/tasks/worker-task-1/requirement-document"
    )


@pytest.mark.asyncio
async def test_requirement_analysis_run_snapshot_uses_requirement_document():
    class FakeRepository:
        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return SimpleNamespace(
                document_type="word",
                document_content="requirement document from saved requirement",
                document_download_url="/v1/requirements/requirement-1/download",
            )

    task = SimpleNamespace(
        task_id="task-1",
        task_type="requirement_analysis",
        name="Analyze requirement",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="requirement-1",
        source_type="manual",
        source_content="task source should not be used",
        instruction="find ambiguities",
    )

    snapshot = await _generation_build_generate_run_snapshot(
        FakeRepository(), "requirement_analysis", task, "run-1", worker_task_id="worker-task-1"
    )

    assert "sourceType" not in snapshot
    assert snapshot["documentType"] == "docx"
    assert snapshot["documentDownloadUrl"] == (
        "/internal/ai-worker/tasks/worker-task-1/requirement-document"
    )
    assert snapshot["sourceContent"] == "requirement document from saved requirement"
    assert snapshot["taskType"] == "requirement_analysis"


@pytest.mark.asyncio
async def test_ui_snapshot_does_not_read_requirement_document_content():
    """UI 三阶段只消费仓库来源与正式用例，历史需求正文不再参与快照组装。"""

    class FakeRepository:
        async def get_requirement(self, requirement_id):
            raise AssertionError("UI 快照不应读取需求正文")

    task = SimpleNamespace(
        task_id="task-1",
        task_type="ui_case_generate",
        name="UI 用例生成",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="requirement-1",
        source_type="repository",
        source_content="",
        instruction="",
    )

    snapshot = await _generation_build_generate_run_snapshot(FakeRepository(), "ui", task, "run-1")

    assert snapshot["sourceContent"] == ""
    assert snapshot["taskType"] == "ui_case_generate"


@pytest.mark.asyncio
async def test_requirement_analysis_task_create_persists_task_without_running(monkeypatch):
    class FakeRepository:
        session = AuthorizationDatabase()

        def __init__(self):
            self.rows = []
            self.task = None

        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return SimpleNamespace(
                requirement_id="requirement-1",
                sprint_id="sprint-1",
                name="Login requirement",
                document_type="richtext",
                document_content="saved requirement text",
            )

        async def get_sprint(self, sprint_id):
            assert sprint_id == "sprint-1"
            return SimpleNamespace(sprint_id="sprint-1", project_id="project-1")

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        def add(self, row):
            self.task = row
            self.rows.append(row)

        def add_all(self, rows):
            raise AssertionError("creating a requirement analysis task should not create runs")

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    ids = iter(["task-1"])
    monkeypatch.setattr(ai_tasks, "new_id", lambda: next(ids))
    repository = FakeRepository()
    service = generation_services(repository)

    payload = await service.commands.create(
        "requirement_analysis",
        "project-1",
        {"requirementId": "requirement-1", "instruction": "find ambiguity"},
        "user-1",
    )

    assert payload["taskId"] == "task-1"
    assert payload["taskType"] == "requirement_analysis"
    assert payload["name"] == "Login requirement analysis"
    assert repository.task.source_type == "richtext"
    assert repository.task.source_content == "saved requirement text"
    assert repository.task.instruction == "find ambiguity"
    assert len(repository.rows) == 1


@pytest.mark.asyncio
async def test_requirement_analysis_list_runs_uses_task_scope(monkeypatch):
    from unittest.mock import AsyncMock

    from testing_agent.services.stage_storage import history_view

    expected = {"total": 0, "items": [], "latestRun": None}
    history = AsyncMock(return_value=expected)
    monkeypatch.setattr(history_view, "direct_history", history)

    class FakeRepository:
        session = AuthorizationDatabase()

        async def get_task(self, task_id):
            assert task_id == "task-1"
            return SimpleNamespace(
                task_id="task-1",
                task_type="requirement_analysis",
                project_id="project-1",
                creator_user_id="user-1",
                requirement_id="",
            )

        async def get_project(self, project_id):
            assert project_id == "project-1"
            return SimpleNamespace(project_id="project-1", user_id="user-1")

    service = generation_services(FakeRepository())
    payload = await service.queries.list_run_summaries("requirement_analysis", "task-1", "user-1")
    assert payload == expected
    history.assert_awaited_once_with(service.queries.repository.session, "task-1", 1, 20, "all")
