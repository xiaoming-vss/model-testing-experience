"""Project collaboration at the real HTTP boundary (real auth, policies and database)."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from support.project_api import (
    account as account,
)
from support.project_api import (
    api as api,
)
from support.project_api import (
    delete_connection as delete_connection,
)
from support.project_api import (
    gitlab_connection as gitlab_connection,
)
from support.project_api import (
    gitlab_remote as gitlab_remote,
)
from support.project_api import (
    project as project,
)
from support.project_api import (
    requirement as requirement,
)
from support.project_api import (
    seed_llm_connection as seed_llm_connection,
)
from support.project_api import (
    seed_requirement_source as seed_requirement_source,
)
from support.project_api import (
    sqlite_longtext as sqlite_longtext,
)
from support.requirement_versions import material_artifact


def seed_approved_understanding(api, rid, headers, connection_id):
    from uuid import uuid4

    base = f"/v1/requirements/{rid}/generation/requirement_analysis/stages/extracting_text"
    launched = api.post(
        base + "/candidate-run", headers=headers, json={"connectionId": connection_id}
    )
    assert launched.status_code == 200, launched.text
    worker = api.post("/internal/ai-worker/tasks/claim", json={"workerId": "material-worker"})
    assert worker.status_code == 200, worker.text
    done = api.post(
        f"/internal/ai-worker/tasks/{worker.json()['taskId']}/completed",
        json={
            "workerId": "material-worker",
            "status": "success",
            "resultYaml": json.dumps(material_artifact(), ensure_ascii=False),
        },
    )
    assert done.status_code == 204, done.text
    candidates = api.get(base + "/candidates", headers=headers).json()["data"]["items"]
    candidate = next(
        item
        for item in candidates
        if item["currentAttemptId"] == launched.json()["data"]["attemptId"]
    )
    current = api.get(base + "/current", headers=headers).json()["data"]
    adopted = api.post(
        base + "/adoption",
        headers=headers,
        json={
            "action": "adopt",
            "candidateId": candidate["candidateId"],
            "expectedCandidateToken": candidate["candidateToken"],
            "expectedAttemptId": candidate["currentAttemptId"],
            "expectedCurrentToken": current["currentToken"],
            "requestId": str(uuid4()),
        },
    )
    assert adopted.status_code == 200, adopted.text


def seed_software_repository(
    api,
    pid,
    repository_id,
    *,
    name,
    group_id="7",
    instance_url="https://gitlab.example",
    remote_project_id="9",
):
    async def seed():
        from testing_agent.models.software_repository import SoftwareRepository
        from testing_agent.services.service_instance import instance_key

        async with api.app.state.test_sessions() as session:
            session.add(
                SoftwareRepository(
                    software_repository_id=repository_id,
                    project_id=pid,
                    name=name,
                    base_path="",
                    repository_project_id=remote_project_id,
                    repository_group_id=group_id,
                    repository_instance_key=instance_key(instance_url),
                    repository_path="team/repo",
                    repository_name="repo",
                    repository_instance_url=instance_url,
                    created_by_user_id="owner",
                )
            )
            await session.commit()

    asyncio.run(seed())


def seed_requirement_software_repository(
    api, rid, repository_id, *, branch="main", baseline_branch="base"
):
    async def seed():
        from testing_agent.models.requirement_software_repository import (
            RequirementSoftwareRepository,
        )

        async with api.app.state.test_sessions() as session:
            session.add(
                RequirementSoftwareRepository(
                    requirement_id=rid,
                    software_repository_id=repository_id,
                    branch=branch,
                    baseline_branch=baseline_branch,
                    created_by_user_id="owner",
                )
            )
            await session.commit()

    asyncio.run(seed())


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
    assert data["permissions"] == ["read", "project_read", "bug_read"]
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
    assert api.delete("/v1/user", headers=owner).status_code == 405
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
    assert api.delete("/v1/user", headers=owner).status_code == 405
    assert api.get("/v1/projects", headers=owner).status_code == 200


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


def test_connection_list_only_returns_the_callers_own_connections(api):
    _, owner = account(api, "owner")
    _, viewer = account(api, "viewer")
    pid = project(api, owner)
    api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "viewer", "role": "viewer"}
    )
    seed_llm_connection(api, owner, project_id=pid, name="owner")
    mine = seed_llm_connection(api, viewer, project_id=pid, name="viewer")
    base = f"/v1/projects/{pid}/integrations/llm/connections"
    items = api.get(base, headers=viewer).json()["data"]["items"]
    assert [item["connectionId"] for item in items] == [mine]
    assert "viewer-secret" not in api.get(base, headers=viewer).text


def test_only_owner_binds_gitlab_and_group_listing_uses_personal_access(api, gitlab_remote):
    _, owner = account(api, "owner")
    _, member = account(api, "member")
    pid = project(api, owner)
    api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
    )
    own = gitlab_connection(api, owner, pid, "owner")
    other = gitlab_connection(api, member, pid, "member")
    body = {
        "name": "订单服务",
        "repository": {
            "connectionId": other,
            "groupId": "7",
            "repositoryId": "101",
        },
    }
    denied = api.post(f"/v1/projects/{pid}/software-repositories", headers=member, json=body)
    assert denied.status_code == 403, denied.text
    remote = f"/v1/projects/{pid}/integrations/gitlab/connections"
    assert api.get(f"{remote}/{own}/groups", headers=member).status_code == 404
    assert api.get(f"{remote}/{other}/groups", headers=member).status_code == 200
    assert gitlab_remote[-1] == ("groups", "https://gitlab.example", "member-token")


def test_zentao_bindings_keep_instance_identity_without_sharing_credentials(api, monkeypatch):
    from testing_agent.services.zentao_mcp import ZentaoMcpResources

    async def remote_project(self, connection, remote_resource_id):
        return SimpleNamespace(id=1, name="remote", deleted=False)

    async def executions(self, connection, remote_project_id, **kwargs):
        return {"items": [{"id": 2, "name": "execution"}], "total": 1}

    async def identity(endpoint, token, **kwargs):
        return {
            "instanceUrl": "https://zentao.example",
            "apiBaseUrl": "https://zentao.example/api.php/v2",
        }

    monkeypatch.setattr("testing_agent.services.shared_service.discover_instance", identity)
    monkeypatch.setattr("testing_agent.services.zentao_mcp.discover_instance", identity)
    monkeypatch.setattr(ZentaoMcpResources, "get_project", remote_project)
    monkeypatch.setattr(ZentaoMcpResources, "list_project_executions", executions)
    _, owner = account(api, "owner")
    _, member = account(api, "member")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)
    sid = api.get(f"/v1/requirements/{rid}", headers=owner).json()["data"]["sprintId"]
    api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
    )
    created = api.post(
        f"/v1/projects/{pid}/services/mcp",
        headers=owner,
        json={
            "name": "zentao",
            "baseUrl": "http://mcp.test/mcp",
            "templateId": "zentao",
            "zentaoInstanceUrl": "https://zentao.example",
        },
    )
    assert created.status_code == 200, created.text
    service_id = created.json()["data"]["serviceId"]
    assert (
        api.put(
            f"/v1/projects/{pid}/services/mcp/{service_id}/authorization",
            headers=owner,
            json={"token": "owner-token"},
        ).status_code
        == 200
    )
    body = {"provider": "zentao", "remoteResourceId": "1"}
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
    seed_requirement_source(api, rid)
    api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
    )
    ids = [
        seed_llm_connection(api, headers, project_id=pid, api_key="personal-key")
        for headers in (owner, member)
    ]
    url = (
        f"/v1/requirements/{rid}/generation/requirement_analysis/stages/extracting_text/"
        "candidate-run"
    )
    assert api.post(url, headers=member, json={"connectionId": ids[0]}).status_code == 404
    response = api.post(url, headers=member, json={"connectionId": ids[1]})
    assert response.status_code == 200, response.text
    chains = api.get(f"/v1/requirements/{rid}/generation", headers=member).json()["data"]["chains"]
    task = next(chain["taskId"] for chain in chains if chain["kind"] == "requirement_analysis")
    assert task
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
    seed_requirement_source(api, rid)
    api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
    )
    cid = seed_llm_connection(
        api,
        member,
        project_id=pid,
        base_url="https://llm.example",
        api_key="private-key",
    )
    response = api.post(
        f"/v1/requirements/{rid}/generation/requirement_analysis/stages/extracting_text/candidate-run",
        headers=member,
        json={"connectionId": cid},
    )
    assert response.status_code == 200, response.text
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
    response = api.get(f"/v1/requirements/{rid}/generation/requirement_analysis", headers=owner)
    assert response.status_code == 200, response.text
    stages = response.json()["data"]["stages"]
    material = next(stage for stage in stages if stage["stage"] == "extracting_text")
    assert material["state"] == "failed"


def test_code_risk_keeps_same_repository_ids_on_different_instances_separate(
    api, gitlab_remote, monkeypatch
):
    from testing_agent.api.deps import verify_worker_token
    from testing_agent.services.gitlab_resource import GitLabResourceClient

    api.app.dependency_overrides[verify_worker_token] = lambda: None

    async def branch(self, base_url, token, repository_id, branch_name, **kwargs):
        return {"name": branch_name, "commitId": "sha"}

    async def gitlab_project(self, base_url, token, repository_id, **kwargs):
        return {
            "id": "9",
            "pathWithNamespace": "team/repo",
            "cloneUrl": f"{base_url}/team/repo.git",
            "defaultBranch": "main",
        }

    async def commit(self, base_url, token, repository_id, ref, **kwargs):
        return "base-sha" if ref == "base" else "head-sha"

    monkeypatch.setattr(GitLabResourceClient, "get_branch", branch)
    monkeypatch.setattr(GitLabResourceClient, "get_project", gitlab_project)
    monkeypatch.setattr(GitLabResourceClient, "resolve_commit", commit)
    _, owner = account(api, "owner")
    _, member = account(api, "member")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)
    seed_requirement_source(api, rid)
    api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
    )
    personal = []
    for index, url in enumerate(("https://first.example", "https://second.example")):
        repository_id = f"repository-{index}"
        seed_software_repository(api, pid, repository_id, name=f"订单服务{index}", instance_url=url)
        seed_requirement_software_repository(api, rid, repository_id)
        personal.append(gitlab_connection(api, member, pid, f"member-{index}", url))
    cid = seed_llm_connection(
        api,
        member,
        project_id=pid,
        base_url="https://llm.example",
        api_key="member-llm",
    )
    seed_approved_understanding(api, rid, member, cid)
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
    delete_connection(api, personal[0])
    assert api.get(f"/internal/ai-worker/tasks/{wid}/gitlab-credentials").status_code == 403


@pytest.mark.parametrize("operation", ["stage-retry", "stage-revise"])
@pytest.mark.parametrize("creator_role", ["owner", "member"])
def test_material_candidate_reexecution_uses_current_actor(api, operation, creator_role):
    from uuid import uuid4

    from testing_agent.api.deps import verify_worker_token

    api.app.dependency_overrides[verify_worker_token] = lambda: None
    _, owner = account(api, "owner")
    _, member = account(api, "member")
    pid = project(api, owner)
    api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
    )
    credentials = {
        role: seed_llm_connection(
            api,
            headers,
            project_id=pid,
            name="llm",
            api_key=f"{role}-key",
            base_url="https://llm.example",
        )
        for role, headers in (("owner", owner), ("member", member))
    }
    rid = requirement(api, owner, pid)
    seed_requirement_source(api, rid)
    actors = {"owner": owner, "member": member}
    operator_role = "member" if creator_role == "owner" else "owner"
    base = f"/v1/requirements/{rid}/generation/requirement_analysis/stages/extracting_text"
    response = api.post(
        base + "/candidate-run",
        headers=actors[creator_role],
        json={"connectionId": credentials[creator_role]},
    )
    assert response.status_code == 200, response.text
    attempt_id = response.json()["data"]["attemptId"]
    claim = api.post("/internal/ai-worker/tasks/claim", json={"workerId": "worker"})
    assert claim.status_code == 200, claim.text
    worker_id = claim.json()["taskId"]
    if operation == "stage-retry":
        response = api.post(
            f"/internal/ai-worker/tasks/{worker_id}/completed",
            json={"workerId": "worker", "status": "failed", "errorMessage": "retryable"},
        )
    else:
        response = api.post(
            f"/internal/ai-worker/tasks/{worker_id}/completed",
            json={
                "workerId": "worker",
                "status": "success",
                "resultYaml": json.dumps(material_artifact(), ensure_ascii=False),
            },
        )
    assert response.status_code == 204, response.text
    body = {"connectionId": credentials[operator_role]}
    if operation == "stage-revise":
        candidates = api.get(base + "/candidates", headers=actors[creator_role]).json()["data"][
            "items"
        ]
        candidate = next(item for item in candidates if item["currentAttemptId"] == attempt_id)
        body.update(
            {
                "instruction": "improve coverage",
                "expectedCandidateToken": candidate["candidateToken"],
                "expectedAttemptId": attempt_id,
                "requestId": str(uuid4()),
            }
        )
        url = base + f"/candidates/{candidate['candidateId']}/revision"
    else:
        url = base + "/candidate-run"
    denied = api.post(
        url, headers=actors[operator_role], json={**body, "connectionId": credentials[creator_role]}
    )
    assert denied.status_code == 404, denied.text
    response = api.post(
        url,
        headers=actors[operator_role],
        json=body,
    )
    assert response.status_code == 200, response.text
    claim = api.post("/internal/ai-worker/tasks/claim", json={"workerId": "worker"})
    assert claim.status_code == 200, claim.text
    new_worker_id = claim.json()["taskId"]
    assert new_worker_id != worker_id
    response = api.get(f"/internal/ai-worker/tasks/{new_worker_id}/llm-credentials")
    assert response.status_code == 200, response.text
    assert response.json()["apiKey"] == f"{operator_role}-key"
