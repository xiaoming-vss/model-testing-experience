"""Project collaboration at the real HTTP boundary (real auth, policies and database)."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from testing_agent.app import create_app
from testing_agent.db.session import get_session
from testing_agent.models import Base


@compiles(LONGTEXT, "sqlite")
def sqlite_longtext(type_, compiler, **kwargs):
    return "TEXT"


@pytest.fixture
def api(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'api.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def initialize():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def session():
        async with sessions() as value:
            yield value

    asyncio.run(initialize())
    from functools import partial

    from testing_agent.services import worker_lease_monitor

    monkeypatch.setattr(
        worker_lease_monitor, "sweep_once", partial(worker_lease_monitor.sweep_once, sessions)
    )
    app = create_app()
    app.state.test_sessions = sessions
    app.dependency_overrides[get_session] = session
    with TestClient(app) as client:
        yield client
    asyncio.run(engine.dispose())


def account(api, name):
    response = api.post("/v1/register", json={"name": name, "password": "test-password"})
    assert response.status_code == 200, response.text
    user = response.json()["data"]
    response = api.post("/v1/login", json={"name": name, "password": "test-password"})
    assert response.status_code == 200, response.text
    return user, {"Authorization": "Bearer " + response.json()["data"]["accessToken"]}


def project(api, headers, name="shared"):
    response = api.post("/v1/projects", headers=headers, json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()["data"]["projectId"]


def test_owner_adds_member_who_can_read_shared_project_but_not_manage_it(api):
    _, owner = account(api, "owner")
    member_user, member = account(api, "member")
    pid = project(api, owner)
    response = api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["userId"] == member_user["userId"]
    shared = api.get(f"/v1/projects/{pid}", headers=member)
    assert shared.status_code == 200, shared.text
    assert shared.json()["data"]["role"] == "member"
    assert [
        p["projectId"] for p in api.get("/v1/projects", headers=member).json()["data"]["items"]
    ] == [pid]
    assert (
        api.patch(f"/v1/projects/{pid}", headers=member, json={"name": "stolen"}).status_code == 403
    )
    assert api.delete(f"/v1/projects/{pid}", headers=member).status_code == 403
    members = api.get(f"/v1/projects/{pid}/members", headers=member)
    assert members.status_code == 200, members.text
    assert {u["role"] for u in members.json()["data"]["items"]} == {"owner", "member"}


def test_membership_is_project_scoped_and_invalid_additions_do_not_change_roles(api):
    _, owner = account(api, "owner")
    _, viewer = account(api, "viewer")
    pid = project(api, owner)
    other = project(api, owner, "private")
    assert (
        api.post(
            f"/v1/projects/{pid}/members", headers=owner, json={"name": "missing", "role": "member"}
        ).status_code
        == 404
    )
    assert (
        api.post(
            f"/v1/projects/{pid}/members", headers=owner, json={"name": "viewer", "role": "owner"}
        ).status_code
        == 400
    )
    assert (
        api.post(
            f"/v1/projects/{pid}/members", headers=owner, json={"name": "viewer", "role": "viewer"}
        ).status_code
        == 200
    )
    assert (
        api.post(
            f"/v1/projects/{pid}/members", headers=owner, json={"name": "viewer", "role": "member"}
        ).status_code
        == 409
    )
    data = api.get(f"/v1/projects/{pid}", headers=viewer).json()["data"]
    assert data["role"] == "viewer"
    assert data["permissions"] == ["read"]
    assert api.get(f"/v1/projects/{other}", headers=viewer).status_code == 403
    assert (
        api.post(
            f"/v1/projects/{pid}/members", headers=viewer, json={"name": "owner", "role": "member"}
        ).status_code
        == 403
    )


def test_transfer_preserves_one_owner_and_removed_member_loses_access(api):
    owner_user, owner = account(api, "owner")
    member_user, member = account(api, "member")
    pid = project(api, owner)
    assert (
        api.post(
            f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "viewer"}
        ).status_code
        == 200
    )
    assert api.delete("/v1/user", headers=owner).status_code == 409
    transfer = api.post(
        f"/v1/projects/{pid}/transfer-ownership",
        headers=owner,
        json={"userId": member_user["userId"]},
    )
    assert transfer.status_code == 200, transfer.text
    assert api.get(f"/v1/projects/{pid}", headers=member).json()["data"]["role"] == "owner"
    assert api.get(f"/v1/projects/{pid}", headers=owner).json()["data"]["role"] == "member"
    assert (
        api.delete(f"/v1/projects/{pid}/members/{owner_user['userId']}", headers=member).status_code
        == 200
    )
    assert api.get(f"/v1/projects/{pid}", headers=owner).status_code == 403
    assert api.delete("/v1/user", headers=owner).status_code == 200
    assert api.get("/v1/projects", headers=owner).status_code == 401


def test_member_creates_shared_sprint_and_viewer_cannot_modify_it(api):
    _, owner = account(api, "owner")
    member_user, member = account(api, "member")
    pid = project(api, owner)
    assert (
        api.post(
            f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
        ).status_code
        == 200
    )
    payload = {
        "name": "iteration",
        "startTime": "2026-09-01T00:00:00Z",
        "endTime": "2026-10-01T00:00:00Z",
    }
    created = api.post(f"/v1/projects/{pid}/sprints", headers=member, json=payload)
    assert created.status_code == 200, created.text
    sid = created.json()["data"]["sprintId"]
    assert (
        api.patch(
            f"/v1/projects/{pid}/members/{member_user['userId']}",
            headers=owner,
            json={"role": "viewer"},
        ).status_code
        == 200
    )
    assert api.get(f"/v1/sprints/{sid}", headers=member).status_code == 200
    assert (
        api.patch(f"/v1/sprints/{sid}", headers=member, json={"name": "changed"}).status_code == 403
    )


def requirement(api, headers, pid):
    response = api.post(
        f"/v1/projects/{pid}/sprints",
        headers=headers,
        json={
            "name": "iteration",
            "startTime": "2026-09-01T00:00:00Z",
            "endTime": "2026-10-01T00:00:00Z",
        },
    )
    assert response.status_code == 200, response.text
    sid = response.json()["data"]["sprintId"]
    response = api.post(f"/v1/sprints/{sid}/requirements", headers=headers, json={"name": "req"})
    assert response.status_code == 200, response.text
    return response.json()["data"]["requirementId"]


@pytest.mark.parametrize(
    "kind,id_key",
    [
        ("function-test-suites", "suiteId"),
        ("api-collections", "collectionId"),
        ("ui-test-suites", "suiteId"),
    ],
)
def test_member_can_maintain_shared_assets_while_viewer_cannot(api, kind, id_key):
    _, owner = account(api, "owner")
    member_user, member = account(api, "member")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)
    assert (
        api.post(
            f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
        ).status_code
        == 200
    )
    created = api.post(f"/v1/requirements/{rid}/{kind}", headers=member, json={"name": "shared"})
    assert created.status_code == 200, created.text
    aid = created.json()["data"][id_key]
    assert (
        api.patch(f"/v1/{kind}/{aid}", headers=member, json={"name": "edited"}).status_code == 200
    )
    assert (
        api.patch(
            f"/v1/projects/{pid}/members/{member_user['userId']}",
            headers=owner,
            json={"role": "viewer"},
        ).status_code
        == 200
    )
    assert api.get(f"/v1/{kind}/{aid}", headers=member).status_code == 200
    assert api.delete(f"/v1/{kind}/{aid}", headers=member).status_code == 403


def test_environment_secrets_are_hidden_and_other_members_cannot_use_them(api):
    _, owner = account(api, "owner")
    _, member = account(api, "member")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)
    api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
    )
    env = api.post(
        f"/v1/projects/{pid}/api-environments",
        headers=owner,
        json={"name": "test", "baseUrl": "https://example.test"},
    ).json()["data"]["environmentId"]
    saved = api.post(
        f"/v1/api-environments/{env}/vars",
        headers=owner,
        json={"varKey": "TOKEN", "value": "private-token", "isSecret": True},
    )
    assert saved.status_code == 200, saved.text
    assert "private-token" not in saved.text
    vid = saved.json()["data"]["envVarId"]
    assert "private-token" not in api.get(f"/v1/api-environments/{env}/vars", headers=member).text
    assert (
        api.patch(
            f"/v1/api-environment-vars/{vid}", headers=member, json={"value": "replaced"}
        ).status_code
        == 403
    )
    collection = api.post(
        f"/v1/requirements/{rid}/api-collections", headers=member, json={"name": "collection"}
    ).json()["data"]["collectionId"]
    response = api.post(
        f"/v1/api-collections/{collection}/run", headers=member, json={"environmentId": env}
    )
    assert response.status_code == 403, response.text

    case = api.post(
        f"/v1/api-collections/{collection}/cases",
        headers=owner,
        json={
            "name": "secret",
            "method": "GET",
            "urlTemplate": "/test",
            "headersJson": {"Authorization": "Bearer {{TOKEN}}"},
        },
    )
    assert case.status_code == 200, case.text
    cid = case.json()["data"]["caseId"]
    response = api.post(f"/v1/api-cases/{cid}/run", headers=owner, json={"environmentId": env})
    assert response.status_code == 200, response.text
    assert "private-token" not in response.text
    run_id = response.json()["data"]["runId"]
    assert "private-token" not in api.get(f"/v1/api-case-runs/{run_id}", headers=member).text

    from testing_agent.api.deps import verify_worker_token

    api.app.dependency_overrides[verify_worker_token] = lambda: None
    claimed = api.post("/internal/api-worker/tasks/claim", json={"workerId": "worker"})
    assert claimed.status_code == 200, claimed.text
    worker_id = claimed.json()["data"]["taskId"]
    snapshot = api.get(f"/internal/api-worker/tasks/{worker_id}/snapshot")
    assert snapshot.status_code == 200, snapshot.text
    assert "private-token" in snapshot.text
    completed = api.post(
        f"/internal/api-worker/tasks/{worker_id}/completed",
        json={
            "workerId": "worker",
            "status": "success",
            "response": {"statusCode": 200, "body": "private-token"},
            "errorMessage": "echo private-token",
        },
    )
    assert completed.status_code == 200, completed.text
    saved_run = api.get(f"/v1/api-case-runs/{run_id}", headers=member)
    assert saved_run.status_code == 200, saved_run.text
    assert "private-token" not in saved_run.text


def test_viewer_manages_own_llm_connection_but_owner_cannot_read_it(api):
    _, owner = account(api, "owner")
    _, viewer = account(api, "viewer")
    pid = project(api, owner)
    api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "viewer", "role": "viewer"}
    )
    base = f"/v1/projects/{pid}/integrations/llm/connections"
    created = api.post(
        base,
        headers=viewer,
        json={
            "name": "mine",
            "baseUrl": "https://llm.example/v1",
            "apiKey": "viewer-secret",
            "modelId": "model",
        },
    )
    assert created.status_code == 200, created.text
    cid = created.json()["data"]["connectionId"]
    assert "viewer-secret" not in created.text
    for invalid_key in ("", "   "):
        updated = api.patch(f"{base}/{cid}", headers=viewer, json={"apiKey": invalid_key})
        assert updated.status_code == 400, updated.text
    assert api.get(f"{base}/{cid}", headers=viewer).status_code == 200
    assert api.get(f"{base}/{cid}", headers=owner).status_code == 404
    assert api.delete(f"{base}/{cid}", headers=owner).status_code == 404


@pytest.fixture
def gitlab_remote(monkeypatch):
    from testing_agent.services.gitlab_auth import GitLabAuthProvider
    from testing_agent.services.gitlab_resource import GitLabResourceClient

    calls = []

    async def validate(self, base_url, access_token):
        calls.append(("auth", base_url, access_token))

    async def group(self, base_url, token, group_id):
        calls.append(("group", base_url, token))
        return {"id": 7, "name": "group"}

    async def groups(self, base_url, token, **kwargs):
        calls.append(("groups", base_url, token))
        return {"items": [{"id": 7, "name": "group"}], "total": 1}

    monkeypatch.setattr(GitLabAuthProvider, "validate", validate)
    monkeypatch.setattr(GitLabResourceClient, "get_group", group)
    monkeypatch.setattr(GitLabResourceClient, "list_groups", groups)
    return calls


def gitlab_connection(api, headers, pid, name, url="https://gitlab.example"):
    response = api.post(
        f"/v1/projects/{pid}/integrations/gitlab/connections",
        headers=headers,
        json={"name": name, "baseUrl": url, "accessToken": name + "-token"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["connectionId"]


def test_only_owner_binds_gitlab_and_binding_does_not_share_remote_access(api, gitlab_remote):
    _, owner = account(api, "owner")
    _, member = account(api, "member")
    pid = project(api, owner)
    api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
    )
    own = gitlab_connection(api, owner, pid, "owner")
    other = gitlab_connection(api, member, pid, "member")
    body = {"provider": "gitlab", "connectionId": other, "remoteResourceId": "7"}
    assert api.post(f"/v1/projects/{pid}/bindings", headers=member, json=body).status_code == 403
    body["connectionId"] = own
    created = api.post(f"/v1/projects/{pid}/bindings", headers=owner, json=body)
    assert created.status_code == 200, created.text
    assert created.json()["data"]["instanceUrl"] == "https://gitlab.example"
    assert api.get(f"/v1/projects/{pid}/bindings", headers=member).status_code == 200
    remote = f"/v1/projects/{pid}/integrations/gitlab/connections"
    assert api.get(f"{remote}/{own}/groups", headers=member).status_code == 404
    assert api.get(f"{remote}/{other}/groups", headers=member).status_code == 200
    assert gitlab_remote[-1] == ("groups", "https://gitlab.example", "member-token")
    second = gitlab_connection(api, owner, pid, "second", "https://second.example")
    body["connectionId"] = second
    assert api.post(f"/v1/projects/{pid}/bindings", headers=owner, json=body).status_code == 200


def test_gitlab_overview_does_not_reuse_another_members_authorization(
    api, gitlab_remote, monkeypatch
):
    from testing_agent.services.gitlab_resource import GitLabResourceClient

    async def scope(self, base_url, token, group_id, repository_id):
        return {"withinGroup": True, "repositoryId": "9"}

    async def compare(self, base_url, token, repository_id, **kwargs):
        gitlab_remote.append(("compare", base_url, token))
        return {"commitsCount": 1, "additions": 3, "deletions": 0}

    monkeypatch.setattr(GitLabResourceClient, "get_repository_group_scope", scope)
    monkeypatch.setattr(GitLabResourceClient, "compare_repository_branches", compare)
    _, owner = account(api, "owner")
    _, member = account(api, "member")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)
    sid = api.get(f"/v1/requirements/{rid}", headers=owner).json()["data"]["sprintId"]
    api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
    )
    cid = gitlab_connection(api, owner, pid, "owner")
    group = api.post(
        f"/v1/projects/{pid}/bindings",
        headers=owner,
        json={"provider": "gitlab", "connectionId": cid, "remoteResourceId": "7"},
    )
    assert group.status_code == 200, group.text
    bound = api.post(
        f"/v1/requirements/{rid}/bindings",
        headers=owner,
        json={
            "provider": "gitlab",
            "connectionId": cid,
            "remoteResourceId": "9",
            "remoteParentId": "7",
            "extraJson": {"branch": "main", "baselineBranch": "base"},
        },
    )
    assert bound.status_code == 200, bound.text
    url = f"/v1/sprints/{sid}/code-overview"
    own = api.get(url, headers=owner)
    assert own.status_code == 200, own.text
    assert gitlab_remote[-1] == ("compare", "https://gitlab.example", "owner-token")
    denied = api.get(url, headers=member)
    assert denied.status_code == 200, denied.text
    assert denied.json()["data"]["repositories"][0]["error"]
    gitlab_connection(api, member, pid, "member")
    assert api.get(url, headers=member).status_code == 200
    assert gitlab_remote[-1] == ("compare", "https://gitlab.example", "member-token")


def test_zentao_bindings_keep_instance_identity_without_sharing_credentials(api, monkeypatch):
    from testing_agent.services.zentao_auth import ZentaoAuthProvider, ZentaoAuthResult
    from testing_agent.services.zentao_resource import ZentaoProjectResource, ZentaoResourceClient

    async def auth(self, base_url, account, password):
        return ZentaoAuthResult(access_token=account + "-token")

    async def remote_project(self, connection, remote_resource_id):
        return ZentaoProjectResource(id=1, name="remote")

    async def executions(self, connection, remote_project_id, **kwargs):
        return {"items": [{"id": 2, "name": "execution"}], "total": 1}

    monkeypatch.setattr(ZentaoAuthProvider, "authenticate", auth)
    monkeypatch.setattr(ZentaoResourceClient, "get_project", remote_project)
    monkeypatch.setattr(ZentaoResourceClient, "list_project_executions", executions)
    _, owner = account(api, "owner")
    _, member = account(api, "member")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)
    sid = api.get(f"/v1/requirements/{rid}", headers=owner).json()["data"]["sprintId"]
    api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
    )
    created = api.post(
        f"/v1/projects/{pid}/integrations/zentao/connections",
        headers=owner,
        json={
            "name": "zentao",
            "baseUrl": "https://zentao.example",
            "account": "owner",
            "password": "secret",
        },
    )
    assert created.status_code == 200, created.text
    cid = created.json()["data"]["connectionId"]
    body = {"provider": "zentao", "connectionId": cid, "remoteResourceId": "1"}
    assert api.post(f"/v1/projects/{pid}/bindings", headers=owner, json=body).status_code == 200
    body["remoteResourceId"] = "invalid"
    invalid = api.post(f"/v1/sprints/{sid}/bindings", headers=owner, json=body)
    assert invalid.status_code == 400, invalid.text
    body["remoteResourceId"] = "2"
    bound = api.post(f"/v1/sprints/{sid}/bindings", headers=owner, json=body)
    assert bound.status_code == 200, bound.text
    assert bound.json()["data"]["instanceUrl"] == "https://zentao.example"
    listed = api.get(f"/v1/sprints/{sid}/bindings", headers=member)
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"]["total"] == 1
    assert api.post(f"/v1/sprints/{sid}/bindings", headers=member, json=body).status_code == 403


def test_shared_ai_task_requires_actor_llm_and_creator_loses_access_on_removal(api):
    _, owner = account(api, "owner")
    user, member = account(api, "member")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)
    api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
    )
    created = api.post(
        f"/v1/projects/{pid}/requirement-analysis-tasks",
        headers=member,
        json={"name": "analysis", "requirementId": rid},
    )
    assert created.status_code == 200, created.text
    task = created.json()["data"]["taskId"]
    base = f"/v1/projects/{pid}/integrations/llm/connections"
    ids = []
    for headers in (owner, member):
        response = api.post(
            base,
            headers=headers,
            json={
                "name": "llm",
                "baseUrl": "https://llm.example/v1",
                "apiKey": "personal-key",
                "modelId": "model",
            },
        )
        assert response.status_code == 200, response.text
        ids.append(response.json()["data"]["connectionId"])
    url = f"/v1/requirement-analysis-tasks/{task}/run"
    assert api.post(url, headers=member, json={"connectionId": ids[0]}).status_code == 404
    response = api.post(url, headers=member, json={"connectionId": ids[1]})
    assert response.status_code == 200, response.text
    api.patch(
        f"/v1/projects/{pid}/members/{user['userId']}", headers=owner, json={"role": "viewer"}
    )
    assert api.post(url, headers=member, json={"connectionId": ids[1]}).status_code == 403
    assert api.get(f"/v1/requirement-analysis-tasks/{task}", headers=member).status_code == 200
    api.delete(f"/v1/projects/{pid}/members/{user['userId']}", headers=owner)
    assert api.get(f"/v1/requirement-analysis-tasks/{task}", headers=member).status_code == 403


def test_worker_credentials_check_current_membership_and_connection_status(api):
    from testing_agent.api.deps import verify_worker_token

    api.app.dependency_overrides[verify_worker_token] = lambda: None
    _, owner = account(api, "owner")
    user, member = account(api, "member")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)
    api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
    )
    cid = api.post(
        f"/v1/projects/{pid}/integrations/llm/connections",
        headers=member,
        json={
            "name": "llm",
            "baseUrl": "https://llm.example",
            "apiKey": "private-key",
            "modelId": "model",
        },
    ).json()["data"]["connectionId"]
    tid = api.post(
        f"/v1/projects/{pid}/requirement-analysis-tasks",
        headers=member,
        json={"name": "analysis", "requirementId": rid},
    ).json()["data"]["taskId"]
    response = api.post(
        f"/v1/requirement-analysis-tasks/{tid}/run", headers=member, json={"connectionId": cid}
    )
    assert response.status_code == 200, response.text
    run_id = response.json()["data"]["runId"]
    response = api.post("/internal/ai-worker/tasks/claim", json={"workerId": "test"})
    assert response.status_code == 200, response.text
    wid = response.json()["taskId"]
    url = f"/internal/ai-worker/tasks/{wid}/llm-credentials"
    response = api.get(url)
    assert response.status_code == 200, response.text
    assert response.json()["apiKey"] == "private-key"
    api.patch(
        f"/v1/projects/{pid}/members/{user['userId']}", headers=owner, json={"role": "viewer"}
    )
    assert api.get(url).status_code == 200  # An already submitted operation survives downgrade.
    api.delete(f"/v1/projects/{pid}/members/{user['userId']}", headers=owner)
    assert api.get(url).status_code == 403
    assert "private-key" not in api.get(url).text
    response = api.get(f"/v1/requirement-analysis-runs/{run_id}", headers=owner)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "failed"


def test_stage_approval_records_new_actor_and_uses_their_llm(api):
    from testing_agent.api.deps import verify_worker_token

    api.app.dependency_overrides[verify_worker_token] = lambda: None
    _, owner = account(api, "owner")
    member_user, member = account(api, "member")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)
    api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
    )
    connections = []
    for headers, key in ((owner, "owner-key"), (member, "member-key")):
        response = api.post(
            f"/v1/projects/{pid}/integrations/llm/connections",
            headers=headers,
            json={
                "name": "llm",
                "apiKey": key,
                "modelId": "model",
                "baseUrl": "https://llm.example",
            },
        )
        connections.append(response.json()["data"]["connectionId"])
    tid = api.post(
        f"/v1/projects/{pid}/requirement-analysis-tasks",
        headers=owner,
        json={"name": "analysis", "requirementId": rid},
    ).json()["data"]["taskId"]
    response = api.post(
        f"/v1/requirement-analysis-tasks/{tid}/run",
        headers=owner,
        json={"connectionId": connections[0], "checkpointEnabled": True},
    )
    assert response.status_code == 200, response.text
    rid_run = response.json()["data"]["runId"]
    wid = api.post("/internal/ai-worker/tasks/claim", json={"workerId": "worker"}).json()["taskId"]
    response = api.patch(
        f"/internal/ai-worker/tasks/{wid}/progress",
        json={
            "workerId": "worker",
            "currentStage": "extracting_text",
            "stageStatus": "waiting_review",
            "configJson": {"firstStepOutput": "extracted requirement"},
        },
    )
    assert response.status_code == 204, response.text
    url = f"/v1/requirement-analysis-runs/{rid_run}/stage-review"
    body = {"stage": "extracting_text", "action": "approve"}
    assert api.post(url, headers=member, json=body).status_code == 404
    response = api.post(url, headers=member, json={**body, "llmConnectionId": connections[1]})
    assert response.status_code == 200, response.text
    response = api.post("/internal/ai-worker/tasks/claim", json={"workerId": "worker"})
    assert response.status_code == 200, response.text
    next_wid = response.json()["taskId"]
    credentials = api.get(f"/internal/ai-worker/tasks/{next_wid}/llm-credentials")
    assert credentials.status_code == 200, credentials.text
    assert credentials.json()["apiKey"] == "member-key"
    api.delete(f"/v1/projects/{pid}/members/{member_user['userId']}", headers=owner)
    assert api.get(f"/internal/ai-worker/tasks/{next_wid}/llm-credentials").status_code == 403


def test_code_risk_keeps_same_repository_ids_on_different_instances_separate(
    api, gitlab_remote, monkeypatch
):
    from testing_agent.api.deps import verify_worker_token
    from testing_agent.services.gitlab_resource import GitLabResourceClient

    api.app.dependency_overrides[verify_worker_token] = lambda: None

    async def scope(self, base_url, token, group_id, repository_id):
        return {"withinGroup": True, "repositoryId": "9"}

    monkeypatch.setattr(GitLabResourceClient, "get_repository_group_scope", scope)
    _, owner = account(api, "owner")
    _, member = account(api, "member")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)
    api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
    )
    personal = []
    for index, url in enumerate(("https://first.example", "https://second.example")):
        cid = gitlab_connection(api, owner, pid, f"owner-{index}", url)
        response = api.post(
            f"/v1/projects/{pid}/bindings",
            headers=owner,
            json={"provider": "gitlab", "connectionId": cid, "remoteResourceId": "7"},
        )
        assert response.status_code == 200, response.text
        response = api.post(
            f"/v1/requirements/{rid}/bindings",
            headers=owner,
            json={
                "provider": "gitlab",
                "connectionId": cid,
                "remoteResourceId": "9",
                "remoteParentId": "7",
                "extraJson": {"branch": "main"},
            },
        )
        assert response.status_code == 200, response.text
        personal.append(gitlab_connection(api, member, pid, f"member-{index}", url))
    cid = api.post(
        f"/v1/projects/{pid}/integrations/llm/connections",
        headers=member,
        json={
            "name": "llm",
            "apiKey": "member-llm",
            "modelId": "model",
            "baseUrl": "https://llm.example",
        },
    ).json()["data"]["connectionId"]
    response = api.post(
        f"/v1/projects/{pid}/code-risk-analysis-tasks",
        headers=member,
        json={"name": "risk", "requirementId": rid},
    )
    assert response.status_code == 200, response.text
    tid = response.json()["data"]["taskId"]
    response = api.post(
        f"/v1/code-risk-analysis-tasks/{tid}/run", headers=member, json={"connectionId": cid}
    )
    assert response.status_code == 200, response.text
    bindings = response.json()["data"]["snapshotJson"]["bindings"]
    assert {b["connectionId"] for b in bindings} == set(personal)
    assert {b["instanceUrl"] for b in bindings} == {
        "https://first.example",
        "https://second.example",
    }
    wid = api.post("/internal/ai-worker/tasks/claim", json={"workerId": "worker"}).json()["taskId"]
    response = api.get(f"/internal/ai-worker/tasks/{wid}/gitlab-credentials")
    assert response.status_code == 200, response.text
    assert {item["accessToken"] for item in response.json()["credentials"]} == {
        "member-0-token",
        "member-1-token",
    }
    assert "owner-" not in response.text
    response = api.delete(
        f"/v1/projects/{pid}/integrations/gitlab/connections/{personal[0]}", headers=member
    )
    assert response.status_code == 200, response.text
    assert api.get(f"/internal/ai-worker/tasks/{wid}/gitlab-credentials").status_code == 403


@pytest.mark.parametrize("operation", ["stage-retry", "stage-revise"])
@pytest.mark.parametrize("creator_role", ["owner", "member"])
def test_function_stage_reexecution_uses_current_actor(api, operation, creator_role):
    from testing_agent.api.deps import verify_worker_token

    api.app.dependency_overrides[verify_worker_token] = lambda: None
    _, owner = account(api, "owner")
    _, member = account(api, "member")
    pid = project(api, owner)
    api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
    )
    credentials = {}
    for role, headers in (("owner", owner), ("member", member)):
        response = api.post(
            f"/v1/projects/{pid}/integrations/llm/connections",
            headers=headers,
            json={
                "name": "llm",
                "apiKey": f"{role}-key",
                "modelId": "model",
                "baseUrl": "https://llm.example",
            },
        )
        assert response.status_code == 200, response.text
        credentials[role] = response.json()["data"]["connectionId"]
    actors = {"owner": owner, "member": member}
    operator_role = "member" if creator_role == "owner" else "owner"
    response = api.post(
        f"/v1/projects/{pid}/function-case-generate-tasks",
        headers=actors[creator_role],
        json={"name": "cases", "sourceType": "text", "sourceContent": "requirement"},
    )
    assert response.status_code == 200, response.text
    tid = response.json()["data"]["taskId"]
    response = api.post(
        f"/v1/function-case-generate-tasks/{tid}/run",
        headers=actors[creator_role],
        json={"connectionId": credentials[creator_role], "checkpointEnabled": True},
    )
    assert response.status_code == 200, response.text
    run_id = response.json()["data"]["runId"]
    claim = api.post("/internal/ai-worker/tasks/claim", json={"workerId": "worker"})
    assert claim.status_code == 200, claim.text
    worker_id = claim.json()["taskId"]
    if operation == "stage-retry":
        response = api.post(
            f"/internal/ai-worker/tasks/{worker_id}/completed",
            json={"workerId": "worker", "status": "failed", "errorMessage": "retryable"},
        )
    else:
        response = api.patch(
            f"/internal/ai-worker/tasks/{worker_id}/progress",
            json={
                "workerId": "worker",
                "currentStage": "requirement_analysis",
                "stageStatus": "waiting_review",
                "configJson": {"requirementAnalysis": {"summary": "test"}},
            },
        )
    assert response.status_code == 204, response.text
    response = api.post(
        f"/v1/function-case-generate-task-runs/{run_id}/{operation}",
        headers=actors[operator_role],
        json={
            "stage": "requirement_analysis",
            "llmConnectionId": credentials[operator_role],
            "revisionInstruction": "improve coverage",
        },
    )
    assert response.status_code == 200, response.text
    claim = api.post("/internal/ai-worker/tasks/claim", json={"workerId": "worker"})
    assert claim.status_code == 200, claim.text
    new_worker_id = claim.json()["taskId"]
    assert new_worker_id != worker_id
    response = api.get(f"/internal/ai-worker/tasks/{new_worker_id}/llm-credentials")
    assert response.status_code == 200, response.text
    assert response.json()["apiKey"] == f"{operator_role}-key"
