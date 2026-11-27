"""Project-visible definitions and personal-only authorizations at the HTTP boundary."""

import pytest
from support.project_api import account, project
from support.project_api import api as api_fixture

api = api_fixture


@pytest.fixture(autouse=True)
def remote_auth(monkeypatch):
    async def gitlab(*args, **kwargs):
        return None

    monkeypatch.setattr("testing_agent.services.gitlab_auth.GitLabAuthProvider.validate", gitlab)


@pytest.mark.parametrize(
    "provider,credentials",
    [
        ("llm", {"apiKey": "only-my-llm-key"}),
        ("gitlab", {"accessToken": "only-my-gitlab-token"}),
    ],
)
def test_shared_visibility_and_separate_personal_authorization(api, provider, credentials):
    _, owner = account(api, "owner")
    _, member = account(api, "member")
    _, outsider = account(api, "outsider")
    pid = project(api, owner)
    assert (
        api.post(
            f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "viewer"}
        ).status_code
        == 200
    )
    path = f"/v1/projects/{pid}/services/{provider}"
    config = {
        "name": "团队服务",
        "baseUrl": "https://example.test",
        "modelId": "model-1" if provider == "llm" else "",
    }
    created = api.post(path, headers=owner, json=config)
    assert created.status_code == 200, created.text
    resource = created.json()["data"]
    assert resource["authorization"]["status"] == "unauthorized"
    sid = resource["serviceId"]
    assert api.get(path, headers=member).json()["data"]["items"][0]["serviceId"] == sid
    assert api.get(path, headers=outsider).status_code in (403, 404)
    assert api.post(path, headers=member, json=config).status_code == 403
    assert api.patch(f"{path}/{sid}", headers=member, json={"name": "hijacked"}).status_code == 403
    # Creation accepts metadata only, never silently treats a key as shared configuration.
    assert api.post(path, headers=owner, json={**config, **credentials}).status_code == 400
    endpoint = f"{path}/{sid}/authorization"
    authorized = api.put(endpoint, headers=member, json=credentials)
    assert authorized.status_code == 200, authorized.text
    mine = authorized.json()["data"]["authorization"]
    assert mine["status"] == "authorized"
    own = api.get(path, headers=owner).json()["data"]["items"][0]
    assert own["authorization"]["status"] == "unauthorized"
    assert mine["connectionId"] not in str(own)
    for key in ("only-my-llm-key", "only-my-gitlab-token"):
        assert key not in str(own)
    # Existing execution selectors see only the current actor's personal connection.
    selector = f"/v1/projects/{pid}/integrations/{provider}/connections"
    assert api.get(selector, headers=owner).json()["data"]["items"] == []
    personal = api.get(selector, headers=member).json()["data"]["items"]
    assert personal[0]["connectionId"] == mine["connectionId"]
    assert personal[0]["name"] == "团队服务"
    # One user's revocation does not revoke somebody else's authorization.
    owner_auth = api.put(endpoint, headers=owner, json=credentials)
    assert owner_auth.status_code == 200
    assert api.delete(endpoint, headers=member).status_code == 200
    assert (
        api.get(path, headers=member).json()["data"]["items"][0]["authorization"]["status"]
        == "unauthorized"
    )
    assert (
        api.get(path, headers=owner).json()["data"]["items"][0]["authorization"]["status"]
        == "authorized"
    )
    assert api.get(selector, headers=member).json()["data"]["items"] == []
    # Authorizing again gets a new personal reference, never a different member's connection.
    renewed = api.put(endpoint, headers=member, json=credentials)
    assert renewed.status_code == 200, renewed.text
    assert renewed.json()["data"]["authorization"]["connectionId"] != mine["connectionId"]
    assert api.delete(f"{path}/{sid}", headers=member).status_code == 403
    assert api.delete(f"{path}/{sid}", headers=owner).status_code == 200
    assert api.get(path, headers=member).json()["data"]["items"] == []
    assert api.get(selector, headers=member).json()["data"]["items"] == []


def test_mcp_authorization_rechecks_endpoint_after_remote_discovery(api, monkeypatch):
    from sqlalchemy import select

    from testing_agent.models.shared_service import SharedService

    _, owner = account(api, "endpoint-owner")
    pid = project(api, owner)
    base = f"/v1/projects/{pid}/services/mcp"
    created = api.post(
        base,
        headers=owner,
        json={"name": "zentao", "baseUrl": "https://mcp.example/mcp", "templateId": "zentao"},
    )
    assert created.status_code == 200, created.text
    service_id = created.json()["data"]["serviceId"]

    async def changed_endpoint(endpoint, token):
        assert endpoint == "https://mcp.example/mcp"
        async with api.app.state.test_sessions() as session:
            row = await session.scalar(
                select(SharedService).where(SharedService.service_id == service_id)
            )
            row.base_url = "https://other-mcp.example/mcp"
            await session.commit()
        return {
            "instanceUrl": "https://zentao.example",
            "apiBaseUrl": "https://zentao.example/api.php/v2",
        }

    monkeypatch.setattr("testing_agent.services.shared_service.discover_instance", changed_endpoint)
    authorized = api.put(
        f"{base}/{service_id}/authorization", headers=owner, json={"token": "fixture"}
    )
    assert authorized.status_code == 409, authorized.text
    assert "服务地址已变更" in authorized.json()["message"]
    listed = api.get(base, headers=owner)
    assert listed.status_code == 200
    assert listed.json()["data"]["items"][0]["authorization"]["status"] == "unauthorized"


def test_shared_service_rejects_http_without_explicit_opt_in(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    response = api.post(
        f"/v1/projects/{pid}/services/gitlab",
        headers=owner,
        json={"name": "内网 GitLab", "baseUrl": "http://gitlab.test"},
    )
    assert response.status_code == 400


def test_shared_service_http_flags_reach_personal_connection(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    base = f"/v1/projects/{pid}/services/gitlab"
    created = api.post(
        base,
        headers=owner,
        json={
            "name": "内网 GitLab",
            "baseUrl": "http://gitlab.test",
            "allowHttp": True,
            "insecureSkipVerify": True,
        },
    )
    assert created.status_code == 200, created.text
    resource = created.json()["data"]
    assert resource["allowHttp"] is True
    assert resource["insecureSkipVerify"] is True
    service_id = resource["serviceId"]
    authorized = api.put(
        f"{base}/{service_id}/authorization",
        headers=owner,
        json={"accessToken": "personal-token"},
    )
    assert authorized.status_code == 200, authorized.text
    connections = api.get(f"/v1/projects/{pid}/integrations/gitlab/connections", headers=owner)
    assert connections.status_code == 200
    personal = connections.json()["data"]["items"][0]
    assert personal["allowHttp"] is True
    assert personal["insecureSkipVerify"] is True
