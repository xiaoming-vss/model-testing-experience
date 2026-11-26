from types import SimpleNamespace

import pytest
from authorization_database import AuthorizationDatabase
from support import generation as ai_tasks
from support.generation import generation_services

from testing_agent.core.errors import (
    ErrBadRequest,
)
from testing_agent.domain.ai_tasks import task_type_for as _generation_task_type_for
from testing_agent.services import worker
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
