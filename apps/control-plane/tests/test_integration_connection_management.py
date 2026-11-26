from types import SimpleNamespace

import pytest
from support.remaining_control_plane import (
    FakeIntegrationConnectionService,
    FakeIntegrationRepositoryForConnectionAuth,
    FakeResourceBindingRepository,
    FakeZentaoAccess,
    FakeZentaoResourceClient,
)

from testing_agent.core.errors import (
    ErrRemoteResourceAlreadyBound,
    ErrResourceBindingAlreadyExists,
    ErrZentaoRemoteResourceUnavailable,
)
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.resource_binding import ResourceBindingService


@pytest.mark.asyncio
async def test_integration_connections_are_scoped_by_project(monkeypatch):
    ids = iter(["connection-1"])
    monkeypatch.setattr("testing_agent.services.integration_connection.new_id", lambda: next(ids))
    repository = FakeIntegrationRepositoryForConnectionAuth()
    repository.project = SimpleNamespace(project_id="project-1", user_id="user-1")

    async def get_project(project_id):
        assert project_id == "project-1"
        return repository.project

    async def scoped_list(user_id, provider, project_id=""):
        return [
            row
            for row in repository.rows
            if row.user_id == user_id and row.provider == provider and row.project_id == project_id
        ]

    repository.get_project = get_project
    repository.list = scoped_list
    service = IntegrationConnectionService(
        repository, credential_cipher=IntegrationCredentialCipher("test-key")
    )

    result = await service.create(
        "llm",
        {
            "name": "LLM",
            "baseUrl": "https://llm.example",
            "modelId": "gpt",
            "apiKey": "key",
        },
        "user-1",
        "project-1",
    )
    repository.rows.append(
        SimpleNamespace(
            connection_id="connection-other",
            project_id="project-2",
            user_id="user-1",
            provider="llm",
            name="Other",
        )
    )

    listed = await service.list("llm", "user-1", "project-1")

    assert result["projectId"] == "project-1"
    assert repository.rows[0].project_id == "project-1"
    assert [item["connectionId"] for item in listed["items"]] == ["connection-1"]


@pytest.mark.asyncio
async def test_project_zentao_binding_uses_go_request_and_updates_project_summary(
    monkeypatch,
):
    ids = iter(["binding-1"])
    monkeypatch.setattr("testing_agent.services.resource_binding.new_id", lambda: next(ids))
    repository = FakeResourceBindingRepository()
    zentao_client = FakeZentaoResourceClient()
    service = ResourceBindingService(
        repository,
        FakeIntegrationConnectionService(),
        zentao_client,
        zentao_access=FakeZentaoAccess(),
    )

    result = await service.create(
        "project",
        "project-1",
        {
            "provider": "zentao",
            "connectionId": "conn-1",
            "remoteResourceId": "101",
        },
        "user-1",
    )

    binding = repository.rows[0]
    assert result["bindingId"] == "binding-1"
    assert result["remoteResourceType"] == "project"
    assert result["remoteResourceId"] == "101"
    assert result["remoteNameSnapshot"] == "旧禅道项目"
    assert result["lastVerifiedAt"] is not None
    assert binding.remote_parent_id == ""
    assert binding.extra_json == {}
    assert zentao_client.project_calls == [("conn-1", "101")]
    assert repository.committed is True
    assert repository.refreshed is binding


@pytest.mark.asyncio
async def test_project_zentao_binding_rejects_existing_active_local_binding():
    repository = FakeResourceBindingRepository()
    repository.active_local = SimpleNamespace(binding_id="existing")
    service = ResourceBindingService(
        repository,
        FakeIntegrationConnectionService(),
        FakeZentaoResourceClient(),
        zentao_access=FakeZentaoAccess(),
    )

    with pytest.raises(type(ErrResourceBindingAlreadyExists)) as exc_info:
        await service.create(
            "project",
            "project-1",
            {
                "provider": "zentao",
                "connectionId": "conn-1",
                "remoteResourceId": "101",
            },
            "user-1",
        )

    assert exc_info.value.code == ErrResourceBindingAlreadyExists.code


@pytest.mark.asyncio
async def test_project_zentao_binding_rejects_existing_active_remote_binding():
    repository = FakeResourceBindingRepository()
    repository.remote_exists = True
    service = ResourceBindingService(
        repository,
        FakeIntegrationConnectionService(),
        FakeZentaoResourceClient(),
        zentao_access=FakeZentaoAccess(),
    )

    with pytest.raises(type(ErrRemoteResourceAlreadyBound)) as exc_info:
        await service.create(
            "project",
            "project-1",
            {
                "provider": "zentao",
                "connectionId": "conn-1",
                "remoteResourceId": "101",
            },
            "user-1",
        )

    assert exc_info.value.code == ErrRemoteResourceAlreadyBound.code


@pytest.mark.asyncio
async def test_project_zentao_binding_rejects_deleted_remote_project():
    repository = FakeResourceBindingRepository()
    service = ResourceBindingService(
        repository,
        FakeIntegrationConnectionService(),
        FakeZentaoResourceClient(deleted=True),
        zentao_access=FakeZentaoAccess(),
    )

    with pytest.raises(type(ErrZentaoRemoteResourceUnavailable)) as exc_info:
        await service.create(
            "project",
            "project-1",
            {
                "provider": "zentao",
                "connectionId": "conn-1",
                "remoteResourceId": "101",
            },
            "user-1",
        )

    assert exc_info.value.code == ErrZentaoRemoteResourceUnavailable.code
    assert "已删除" in exc_info.value.message
