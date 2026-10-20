"""Built-in MCP management never shares credentials or enables task execution."""

import asyncio

import pytest
from sqlalchemy import select
from support.project_api import account, project
from support.project_api import api as api_fixture

from testing_agent.core.config import get_settings
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.shared_service import ServiceAuthorization
from testing_agent.services.integration_credentials import IntegrationCredentialCipher


@pytest.fixture
def api(tmp_path, monkeypatch):
    import json

    import httpx

    from testing_agent.services.mcp_client import McpClient

    def handle(request):
        body = json.loads(request.content)
        if body["method"] == "notifications/initialized":
            return httpx.Response(202)
        result = (
            {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}}
            if body["method"] == "initialize"
            else {
                "structuredContent": {
                    "schemaVersion": 1,
                    "instanceUrl": "https://zentao.test",
                    "apiBaseUrl": "https://zentao.test/api.php/v2",
                }
            }
        )
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    monkeypatch.setattr(
        "testing_agent.services.zentao_mcp_instance.McpClient",
        lambda url, token: McpClient(url, token, transport=httpx.MockTransport(handle)),
    )
    yield from api_fixture.__wrapped__(tmp_path, monkeypatch)


def setup_service(api):
    _, owner = account(api, "owner")
    _, member = account(api, "member")
    _, outsider = account(api, "outsider")
    pid = project(api, owner)
    assert (
        api.post(
            f"/v1/projects/{pid}/members",
            headers=owner,
            json={"name": "member", "role": "viewer"},
        ).status_code
        == 200
    )
    path = f"/v1/projects/{pid}/services/mcp"
    config = {
        "name": "ZenTao-MCP",
        "baseUrl": "http://127.0.0.1:9090/zentao/mcp",
        "templateId": "zentao",
    }
    return owner, member, outsider, path, config


def test_builtin_catalog_and_personal_credential_lifecycle(api):
    owner, member, outsider, path, config = setup_service(api)
    templates = api.get(f"{path}/templates", headers=member)
    assert templates.status_code == 200
    assert templates.json()["data"]["items"] == [
        {
            "templateId": "zentao",
            "name": "ZenTao-MCP",
            "type": "streamableHttp",
            "authorizationHeader": "token",
        }
    ]
    assert api.get(path, headers=member).json()["data"]["items"] == []
    assert api.get(f"{path}/templates", headers=outsider).status_code in (403, 404)
    assert api.post(path, headers=member, json=config).status_code == 403
    created = api.post(path, headers=owner, json=config)
    assert created.status_code == 200, created.text
    resource = created.json()["data"]
    assert resource["baseUrl"] == config["baseUrl"]
    assert resource["templateId"] == "zentao"
    sid = resource["serviceId"]
    endpoint = f"{path}/{sid}/authorization"
    # MCP names are unique; projects can now configure multiple named MCP services.
    assert api.post(path, headers=owner, json=config).status_code == 409
    assert (
        api.patch(
            f"{path}/{sid}",
            headers=member,
            json={"name": "ZenTao-MCP", "baseUrl": "http://other.test/mcp"},
        ).status_code
        == 403
    )
    assert api.patch(f"{path}/{sid}", headers=member, json={"name": "other"}).status_code == 403
    renamed = api.patch(f"{path}/{sid}", headers=owner, json={"name": "项目禅道"})
    assert renamed.json()["data"]["name"] == "项目禅道"
    assert api.put(endpoint, headers=outsider, json={"token": "foreign"}).status_code in (403, 404)
    for invalid in ({"token": " "}, {"apiKey": "wrong"}, {"token": "ok", "password": "no"}):
        assert api.put(endpoint, headers=member, json=invalid).status_code == 400
    auth = api.put(endpoint, headers=member, json={"token": "member-secret"})
    assert auth.status_code == 200, auth.text
    cid = auth.json()["data"]["authorization"]["connectionId"]
    assert "member-secret" not in auth.text
    visible = api.get(path, headers=owner)
    assert cid not in visible.text and "member-secret" not in visible.text
    assert visible.json()["data"]["items"][0]["authorization"]["status"] == "unauthorized"
    updated = api.put(endpoint, headers=member, json={"token": "updated-secret"})
    assert updated.json()["data"]["authorization"]["connectionId"] == cid

    async def inspect_secret():
        async with api.app.state.test_sessions() as session:
            connection = await session.scalar(
                select(IntegrationConnection).where(IntegrationConnection.connection_id == cid)
            )
            assert connection.provider == "mcp"
            assert connection.auth_type == "mcp_header_token"
            assert connection.access_token == ""
            cipher = IntegrationCredentialCipher(get_settings().integration_key)
            assert cipher.decrypt(connection.secret_json["token"]) == "updated-secret"
            assert "updated-secret" not in str(connection.extra_json)

    asyncio.run(inspect_secret())

    assert api.put(endpoint, headers=owner, json={"token": "owner-secret"}).status_code == 200
    assert (
        api.delete(endpoint, headers=member).json()["data"]["authorization"]["status"]
        == "unauthorized"
    )
    assert (
        api.get(path, headers=owner).json()["data"]["items"][0]["authorization"]["status"]
        == "authorized"
    )
    renewed = api.put(endpoint, headers=member, json={"token": "new-secret"})
    assert renewed.json()["data"]["authorization"]["connectionId"] != cid
    assert api.delete(f"{path}/{sid}", headers=member).status_code == 403
    assert api.delete(f"{path}/{sid}", headers=owner).status_code == 200
    assert api.put(endpoint, headers=member, json={"token": "stale"}).status_code == 404
    assert api.get(path, headers=member).json()["data"]["items"] == []

    async def inspect_deleted():
        async with api.app.state.test_sessions() as session:
            assert list(await session.scalars(select(IntegrationConnection))) == []
            assert list(await session.scalars(select(ServiceAuthorization))) == []

    asyncio.run(inspect_deleted())
    recreated = api.post(path, headers=owner, json=config)
    assert recreated.status_code == 200
    assert recreated.json()["data"]["serviceId"] != sid
    assert recreated.json()["data"]["authorization"]["status"] == "unauthorized"


@pytest.mark.parametrize(
    "changes",
    [
        {"templateId": None},
        {"templateId": "custom"},
        {"modelId": "some-model"},
        {"type": "stdio"},
        {"token": "must-not-be-public"},
        {"baseUrl": "ftp://example.test/mcp"},
        {"baseUrl": "https://u:p@example.test/mcp"},
        {"baseUrl": "https://example.test/mcp?token=secret"},
        {"baseUrl": "https://example.test/mcp#fragment"},
        {"baseUrl": "http://bad host/mcp"},
    ],
)
def test_rejects_custom_templates_public_credentials_and_invalid_urls(api, changes):
    owner, _, _, path, config = setup_service(api)
    response = api.post(path, headers=owner, json={**config, **changes})
    assert response.status_code == 400, response.text
    assert api.get(path, headers=owner).json()["data"]["items"] == []


def test_mcp_is_project_scoped_and_separate_from_existing_zentao_connections(api):
    owner, member, _, path, config = setup_service(api)
    created = api.post(path, headers=owner, json=config).json()["data"]
    sid = created["serviceId"]
    other_pid = project(api, owner, "other-project")
    other_path = f"/v1/projects/{other_pid}/services/mcp"
    assert api.post(other_path, headers=owner, json=config).status_code == 200
    assert api.get(other_path, headers=member).status_code in (403, 404)
    assert (
        api.put(
            f"{other_path}/{sid}/authorization", headers=owner, json={"token": "wrong-project"}
        ).status_code
        == 404
    )
    assert (
        api.put(
            f"{path}/{sid}/authorization", headers=owner, json={"token": "owner-token"}
        ).status_code
        == 200
    )
    pid = created["projectId"]
    for provider in ("zentao", "llm"):
        assert (
            api.get(
                f"/v1/projects/{pid}/integrations/{provider}/connections", headers=owner
            ).json()["data"]["items"]
            == []
        )


def test_mcp_preserves_project_endpoint_path_and_trailing_slash(api):
    owner, _, _, path, config = setup_service(api)
    result = api.post(
        path, headers=owner, json={**config, "baseUrl": "https://other.test/nested/mcp/"}
    )
    assert result.status_code == 200
    assert result.json()["data"]["baseUrl"] == "https://other.test/nested/mcp/"
