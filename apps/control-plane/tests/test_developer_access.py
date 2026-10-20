"""Developer access is enforced at the HTTP boundary, independent of navigation."""

from support.bug_api import activities_of, create_bug, transition
from support.function_case_library import make_requirement, make_sprint
from support.project_api import account, project, requirement, seed_requirement_source
from support.project_api import api as api

from testing_agent.api.deps import verify_worker_token


def test_developer_handles_project_bugs_but_cannot_access_other_modules(api):
    owner_user, owner = account(api, "owner")
    developer_user, developer = account(api, "developer")
    _, outsider = account(api, "outsider")
    pid = project(api, owner)
    sid = make_sprint(api, owner, pid)
    rid = make_requirement(api, owner, sid)
    assert (
        api.post(
            f"/v1/projects/{pid}/members",
            headers=owner,
            json={"name": "developer", "role": "developer"},
        ).status_code
        == 200
    )
    bug = create_bug(
        api,
        owner,
        pid,
        sid,
        reporter=owner_user,
        assigneeUserId=developer_user["userId"],
        requirementId=rid,
    )
    bug_id = bug["bugId"]
    access = api.get(f"/v1/projects/{pid}", headers=developer).json()["data"]
    assert access["role"] == "developer"
    assert access["permissions"] == ["project_read", "bug_read", "bug_handle"]
    assert api.get("/v1/projects", headers=developer).json()["data"]["items"][0]["projectId"] == pid
    assert api.get(f"/v1/projects/{pid}/bugs", headers=developer).status_code == 200
    assert api.get(f"/v1/bugs/{bug_id}", headers=developer).status_code == 200
    options = api.get(f"/v1/projects/{pid}/bugs/options", headers=developer)
    assert options.status_code == 200, options.text
    assert options.json()["data"] == {
        "members": [
            {"userId": developer_user["userId"], "name": "developer"},
            {"userId": owner_user["userId"], "name": "owner"},
        ],
        "sprints": [{"sprintId": sid, "name": "iteration"}],
    }
    assert (
        api.post(
            f"/v1/bugs/{bug_id}/comments", headers=developer, json={"content": "已定位问题"}
        ).status_code
        == 200
    )
    assert transition(api, developer, bug_id, "confirm").status_code == 200
    assert transition(api, developer, bug_id, "submit_fix", content="已修复").status_code == 200
    transferred = api.post(
        f"/v1/bugs/{bug_id}/transfer",
        headers=developer,
        json={"assigneeUserId": owner_user["userId"]},
    )
    assert transferred.status_code == 200
    assert transferred.json()["data"]["assigneeUserId"] == owner_user["userId"]
    assert any(
        item["actorUserId"] == developer_user["userId"]
        for item in activities_of(api, developer, bug_id)["items"]
    )
    assert (
        api.post(
            f"/v1/projects/{pid}/bugs", headers=developer, json={"title": "不应创建"}
        ).status_code
        == 403
    )
    assert (
        api.patch(f"/v1/bugs/{bug_id}", headers=developer, json={"title": "不应修改"}).status_code
        == 403
    )
    denied_paths = [
        f"/v1/projects/{pid}/sprints",
        f"/v1/sprints/{sid}",
        f"/v1/sprints/{sid}/requirements",
        f"/v1/requirements/{rid}",
        f"/v1/requirements/{rid}/function-test-suites",
        f"/v1/requirements/{rid}/api-collections",
        f"/v1/requirements/{rid}/ui-test-suites",
        f"/v1/projects/{pid}/test-orders",
        f"/v1/projects/{pid}/api-environments",
        f"/v1/projects/{pid}/function-case-generate-tasks",
        f"/v1/projects/{pid}/services/llm",
        f"/v1/projects/{pid}/members",
        f"/v1/projects/{pid}/skills",
    ]
    for path in denied_paths:
        response = api.get(path, headers=developer)
        assert response.status_code == 403, (path, response.text)
    assert (
        api.patch(f"/v1/projects/{pid}", headers=developer, json={"name": "不应修改"}).status_code
        == 403
    )
    assert (
        api.post(
            f"/v1/bugs/{bug_id}/transfer", headers=developer, json={"assigneeUserId": "outsider"}
        ).status_code
        == 400
    )
    for path in [
        f"/v1/projects/{pid}/bugs",
        f"/v1/projects/{pid}/bugs/options",
        f"/v1/bugs/{bug_id}",
        f"/v1/bugs/{bug_id}/activities",
    ]:
        assert api.get(path, headers=outsider).status_code == 403


def test_developer_role_changes_and_project_membership_are_independent(api):
    owner_user, owner = account(api, "owner")
    user, developer = account(api, "developer")
    pid = project(api, owner)
    other = project(api, owner, "other")
    sid = make_sprint(api, owner, pid)
    other_sid = make_sprint(api, owner, other)
    bug_id = create_bug(api, owner, pid, sid, reporter=owner_user)["bugId"]
    other_bug = create_bug(api, owner, other, other_sid, reporter=owner_user)["bugId"]
    for project_id, role in [(pid, "developer"), (other, "member")]:
        assert (
            api.post(
                f"/v1/projects/{project_id}/members",
                headers=owner,
                json={"name": "developer", "role": role},
            ).status_code
            == 200
        )
    assert api.get(f"/v1/projects/{pid}/sprints", headers=developer).status_code == 403
    assert api.get(f"/v1/projects/{other}/sprints", headers=developer).status_code == 200
    assert (
        api.patch(
            f"/v1/bugs/{other_bug}", headers=developer, json={"title": "普通成员可修改"}
        ).status_code
        == 200
    )
    assert (
        api.patch(
            f"/v1/projects/{pid}/members/{user['userId']}", headers=owner, json={"role": "viewer"}
        ).status_code
        == 200
    )
    assert (
        api.post(
            f"/v1/bugs/{bug_id}/comments", headers=developer, json={"content": "只读不能评论"}
        ).status_code
        == 403
    )
    assert api.get(f"/v1/bugs/{bug_id}", headers=developer).status_code == 200
    assert (
        api.patch(
            f"/v1/projects/{pid}/members/{user['userId']}",
            headers=owner,
            json={"role": "developer"},
        ).status_code
        == 200
    )
    assert api.post(f"/v1/projects/{pid}/leave", headers=developer).status_code == 200
    assert api.get(f"/v1/bugs/{bug_id}", headers=developer).status_code == 403
    assert api.get(f"/v1/bugs/{other_bug}", headers=developer).status_code == 200


def test_downgrade_to_developer_revokes_worker_access_even_after_repromotion(api):
    api.app.dependency_overrides[verify_worker_token] = lambda: None
    _, owner = account(api, "owner")
    user, member = account(api, "member")
    pid = project(api, owner)
    rid = requirement(api, owner, pid)
    seed_requirement_source(api, rid)
    assert (
        api.post(
            f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
        ).status_code
        == 200
    )
    cid = api.post(
        f"/v1/projects/{pid}/integrations/llm/connections",
        headers=member,
        json={
            "name": "llm",
            "baseUrl": "https://llm.example",
            "apiKey": "private",
            "modelId": "model",
        },
    ).json()["data"]["connectionId"]
    tid = api.post(
        f"/v1/projects/{pid}/requirement-analysis-tasks",
        headers=member,
        json={"name": "analysis", "requirementId": rid},
    ).json()["data"]["taskId"]
    run = api.post(
        f"/v1/requirement-analysis-tasks/{tid}/run", headers=member, json={"connectionId": cid}
    ).json()["data"]["runId"]
    wid = api.post("/internal/ai-worker/tasks/claim", json={"workerId": "worker"}).json()["taskId"]
    url = f"/internal/ai-worker/tasks/{wid}/llm-credentials"
    assert api.get(url).status_code == 200
    assert (
        api.patch(
            f"/v1/projects/{pid}/members/{user['userId']}",
            headers=owner,
            json={"role": "developer"},
        ).status_code
        == 200
    )
    assert api.get(url).status_code == 403
    assert (
        api.get(f"/v1/requirement-analysis-runs/{run}", headers=owner).json()["data"]["status"]
        == "failed"
    )
    assert (
        api.patch(
            f"/v1/projects/{pid}/members/{user['userId']}", headers=owner, json={"role": "member"}
        ).status_code
        == 200
    )
    assert api.get(url).status_code == 403
