"""Project-visible definitions and personal-only authorizations at the HTTP boundary."""

from types import SimpleNamespace

import pytest
from test_project_membership_api import account, project
from test_project_membership_api import api as api_fixture

api = api_fixture


@pytest.fixture(autouse=True)
def remote_auth(monkeypatch):
    async def gitlab(*args, **kwargs):
        return None

    async def zentao(*args, **kwargs):
        return SimpleNamespace(access_token="personal-remote-token")

    monkeypatch.setattr("testing_agent.services.gitlab_auth.GitLabAuthProvider.validate", gitlab)
    monkeypatch.setattr(
        "testing_agent.services.zentao_auth.ZentaoAuthProvider.authenticate", zentao
    )


@pytest.mark.parametrize(
    "provider,credentials",
    [
        ("llm", {"apiKey": "only-my-llm-key"}),
        ("gitlab", {"accessToken": "only-my-gitlab-token"}),
        ("zentao", {"account": "personal-account", "password": "only-my-password"}),
    ],
)
def test_shared_visibility_and_separate_personal_authorization(api, provider, credentials):
    _, owner = account(api, "owner")
    member_user, member = account(api, "member")
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
    for key in ("only-my-llm-key", "only-my-gitlab-token", "only-my-password", "personal-account"):
        assert key not in str(own)
    # Existing execution selectors see only the current actor's personal connection.
    selector = f"/v1/projects/{pid}/integrations/{provider}/connections"
    assert api.get(selector, headers=owner).json()["data"]["items"] == []
    personal = api.get(selector, headers=member).json()["data"]["items"]
    assert personal[0]["connectionId"] == mine["connectionId"]
    assert personal[0]["name"] == "团队服务"
    assert (
        api.patch(
            f"{selector}/{mine['connectionId']}",
            headers=member,
            json={"baseUrl": "https://evil.test"},
        ).status_code
        == 400
    )
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
