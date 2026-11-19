from types import SimpleNamespace

import pytest
from support.remaining_control_plane import (
    FakeIntegrationConnectionService,
    FakeIntegrationRepositoryForConnectionAuth,
    FakeIntegrationRepositoryForZentaoBrowse,
    FakeResourceBindingRepository,
    FakeZentaoAccess,
    FakeZentaoAuthHttpClient,
    FakeZentaoAuthProvider,
    FakeZentaoBrowseClient,
    FakeZentaoResourceClient,
)

from testing_agent.core.errors import (
    AppError,
    ErrRemoteResourceAlreadyBound,
    ErrResourceBindingAlreadyExists,
    ErrZentaoRemoteResourceUnavailable,
)
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.resource_binding import ResourceBindingService
from testing_agent.services.zentao_auth import ZentaoAuthProvider


async def test_zentao_auth_provider_verifies_ssl_by_default(monkeypatch):
    monkeypatch.setattr(
        "testing_agent.services.zentao_auth.httpx.AsyncClient",
        FakeZentaoAuthHttpClient,
    )

    result = await ZentaoAuthProvider().authenticate(
        "https://zentao.example",
        "tester",
        "secret",
    )

    assert result.access_token == "token-ssl"
    assert FakeZentaoAuthHttpClient.kwargs["verify"] is True


@pytest.mark.asyncio
async def test_zentao_auth_provider_allows_explicit_insecure_skip(monkeypatch):
    monkeypatch.setattr(
        "testing_agent.services.zentao_auth.httpx.AsyncClient",
        FakeZentaoAuthHttpClient,
    )

    await ZentaoAuthProvider().authenticate(
        "https://zentao.example",
        "tester",
        "secret",
        insecure_skip_verify=True,
    )

    assert FakeZentaoAuthHttpClient.kwargs["verify"] is False


@pytest.mark.asyncio
async def test_zentao_auth_provider_rejects_http_without_opt_in():
    with pytest.raises(ValueError, match="allowHttp"):
        await ZentaoAuthProvider().authenticate(
            "http://zentao.example",
            "tester",
            "secret",
        )


@pytest.mark.asyncio
async def test_zentao_auth_provider_allows_explicit_http(monkeypatch):
    monkeypatch.setattr(
        "testing_agent.services.zentao_auth.httpx.AsyncClient",
        FakeZentaoAuthHttpClient,
    )

    await ZentaoAuthProvider().authenticate(
        "http://zentao.example",
        "tester",
        "secret",
        allow_http=True,
    )

    assert FakeZentaoAuthHttpClient.kwargs["verify"] is True


@pytest.mark.asyncio
async def test_create_zentao_connection_authenticates_and_stores_token(monkeypatch):
    ids = iter(["connection-1"])
    monkeypatch.setattr("testing_agent.services.integration_connection.new_id", lambda: next(ids))
    repository = FakeIntegrationRepositoryForConnectionAuth()
    auth_provider = FakeZentaoAuthProvider()
    service = IntegrationConnectionService(
        repository,
        zentao_auth_provider=auth_provider,
        credential_cipher=IntegrationCredentialCipher("test-key"),
    )

    result = await service.create(
        "zentao",
        {
            "name": "公司禅道",
            "baseUrl": "https://zentao.example",
            "account": "tester",
            "password": "secret",
        },
        "user-1",
    )

    assert auth_provider.calls == [
        (
            "https://zentao.example",
            "tester",
            "secret",
            {"allow_http": False, "insecure_skip_verify": False},
        )
    ]
    assert repository.rows[0].access_token == "token-1"
    assert repository.rows[0].auth_type == "account_password"
    assert repository.rows[0].last_auth_at is not None
    assert result["connectionId"] == "connection-1"
    assert result["hasAccessToken"] is True


@pytest.mark.asyncio
async def test_create_zentao_connection_requires_explicit_http_opt_in():
    repository = FakeIntegrationRepositoryForConnectionAuth()
    service = IntegrationConnectionService(
        repository,
        zentao_auth_provider=FakeZentaoAuthProvider(),
        credential_cipher=IntegrationCredentialCipher("test-key"),
    )

    with pytest.raises(AppError) as exc:
        await service.create(
            "zentao",
            {
                "name": "公司禅道",
                "baseUrl": "http://zentao.example",
                "account": "tester",
                "password": "secret",
            },
            "user-1",
        )
    assert exc.value.http_code == 400
    assert repository.rows == []


@pytest.mark.asyncio
async def test_create_zentao_connection_persists_security_flags(monkeypatch):
    ids = iter(["connection-1"])
    monkeypatch.setattr("testing_agent.services.integration_connection.new_id", lambda: next(ids))
    repository = FakeIntegrationRepositoryForConnectionAuth()
    auth_provider = FakeZentaoAuthProvider()
    service = IntegrationConnectionService(
        repository,
        zentao_auth_provider=auth_provider,
        credential_cipher=IntegrationCredentialCipher("test-key"),
    )

    result = await service.create(
        "zentao",
        {
            "name": "公司禅道",
            "baseUrl": "http://zentao.example",
            "account": "tester",
            "password": "secret",
            "allowHttp": True,
            "insecureSkipVerify": True,
        },
        "user-1",
    )

    assert result["allowHttp"] is True
    assert result["insecureSkipVerify"] is True
    assert repository.rows[0].extra_json == {
        "allowHttp": True,
        "insecureSkipVerify": True,
    }
    assert auth_provider.calls[0][3] == {
        "allow_http": True,
        "insecure_skip_verify": True,
    }


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


@pytest.mark.asyncio
async def test_zentao_candidate_lists_are_loaded_from_remote_client():
    client = FakeZentaoBrowseClient()
    service = IntegrationConnectionService(
        FakeIntegrationRepositoryForZentaoBrowse(),
        client,
    )

    projects = await service.list_zentao_projects("conn-1", "user-1", page=2, page_size=50)
    executions = await service.list_zentao_project_executions(
        "conn-1",
        "101",
        "user-1",
        page=3,
        page_size=40,
    )
    testtasks = await service.list_zentao_execution_testtasks(
        "conn-1",
        "201",
        "user-1",
        page=4,
        page_size=30,
    )
    stories = await service.list_zentao_execution_stories("conn-1", "201", "user-1")
    cases = await service.list_zentao_execution_cases(
        "conn-1",
        "201",
        "user-1",
        page=5,
        page_size=20,
    )

    assert projects == {
        "connectionId": "conn-1",
        "items": [
            {
                "id": 101,
                "name": "项目A",
                "code": "PA",
                "description": "desc",
                "status": "doing",
                "begin": "2026-01-01",
                "end": "2026-02-01",
                "createdAt": "2026-01-01T00:00:00Z",
                "updatedAt": "2026-01-02T00:00:00Z",
            }
        ],
        "total": 2,
    }
    assert executions["items"] == [
        {
            "id": 201,
            "projectId": 101,
            "name": "执行A",
            "description": "exec desc",
            "status": "doing",
            "begin": "2026-01-03",
            "end": "2026-01-20",
            "createdAt": "",
            "updatedAt": "",
        }
    ]
    assert executions["remoteProjectId"] == "101"
    assert testtasks["items"][0]["executionId"] == 201
    assert testtasks["items"][0]["title"] == "测试单标题"
    assert stories["items"][0]["title"] == "需求A"
    assert stories["items"][0]["productId"] == 1
    assert cases["items"][0]["title"] == "用例A"
    assert cases["items"][0]["expectedResults"] == "预期"
    assert client.calls == [
        ("projects", "conn-1", 2, 50),
        ("executions", "conn-1", "101", 3, 40),
        ("testtasks", "conn-1", "201", 4, 30),
        ("stories", "conn-1", "201"),
        ("cases", "conn-1", "201", 5, 20),
    ]
