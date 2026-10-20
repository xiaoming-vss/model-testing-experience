from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from testing_agent.core.errors import (
    ErrIntegrationConnectionAuthFailed,
    ErrZentaoRemoteResourceUnavailable,
)
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.zentao_auth import ZentaoAuthResult


def setup_service(*, client, auth):
    cipher = IntegrationCredentialCipher("zentao-query-test-key")
    row = IntegrationConnection(
        connection_id="personal",
        user_id="owner",
        provider="zentao",
        project_id="",
        name="Zentao",
        base_url="https://zentao.test",
        account="tester",
        access_token="",
        status="active",
        secret_json={"password": cipher.encrypt("test-password")},
    )
    repository = SimpleNamespace(get=AsyncMock(return_value=row), commit=AsyncMock())
    service = IntegrationConnectionService(
        repository,
        zentao_resource_client=client,
        zentao_auth_provider=auth,
        credential_cipher=cipher,
    )
    return service, repository, row


async def test_zentao_query_refreshes_and_commits_auth_before_remote_read():
    auth = SimpleNamespace(authenticate=AsyncMock(return_value=ZentaoAuthResult("fresh-token")))
    client = SimpleNamespace(list_projects=AsyncMock())
    service, repository, row = setup_service(client=client, auth=auth)

    async def read(connection, page, page_size):
        assert repository.commit.await_count == 1
        assert connection.access_token == "fresh-token"
        assert (page, page_size) == (2, 20)
        return {
            "items": [{"id": "kept", "name": "Visible"}, {"id": "gone", "deleted": True}],
            "total": 10,
        }

    client.list_projects.side_effect = read
    result = await service.list_zentao_projects("personal", "owner", page=2, page_size=20)
    assert [item["id"] for item in result["items"]] == ["kept"]
    assert result["total"] == 10
    assert result["connectionId"] == "personal"
    assert row.status == "active"
    auth.authenticate.assert_awaited_once_with("https://zentao.test", "tester", "test-password")


async def test_zentao_failed_refresh_records_auth_failure_without_resource_read():
    auth = SimpleNamespace(
        authenticate=AsyncMock(side_effect=RuntimeError("authentication failed"))
    )
    client = SimpleNamespace(list_projects=AsyncMock())
    service, repository, row = setup_service(client=client, auth=auth)
    with pytest.raises(type(ErrIntegrationConnectionAuthFailed)):
        await service.list_zentao_projects("personal", "owner")
    assert row.status == "auth_failed"
    assert row.access_token == ""
    repository.commit.assert_awaited_once()
    client.list_projects.assert_not_awaited()


async def test_missing_resource_adapter_does_not_refresh_credentials():
    auth = SimpleNamespace(authenticate=AsyncMock())
    service, repository, _ = setup_service(client=None, auth=auth)
    with pytest.raises(type(ErrZentaoRemoteResourceUnavailable)):
        await service.list_zentao_projects("personal", "owner")
    auth.authenticate.assert_not_awaited()
    repository.commit.assert_not_awaited()
