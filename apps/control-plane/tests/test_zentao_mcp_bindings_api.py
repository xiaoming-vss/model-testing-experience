"""Exercise real authentication, binding persistence and MCP transport together."""

import asyncio
import json

import httpx
import pytest
from sqlalchemy import select
from support.project_api import account, project
from support.project_api import api as api
from test_function_case_library import make_requirement, make_sprint

from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.services.mcp_client import McpClient


class Remote:
    def __init__(self):
        self.calls = []
        self.tokens = []
        self.mode = ""
        self.targets = {}

    async def handle(self, request):
        body = json.loads(request.content)
        self.tokens.append(request.headers.get("token"))
        if body["method"] == "notifications/initialized":
            return httpx.Response(202)
        if body["method"] == "initialize":
            result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}}
        else:
            name, args = body["params"]["name"], body["params"]["arguments"]
            if name != "get_zentao_instance":
                self.calls.append((name, args))
            assert name.startswith("get_")  # Binding must never write to Zentao.
            if name == "get_zentao_instance":
                data = {
                    "schemaVersion": 1,
                    "instanceUrl": self.targets.get(request.url.host, "http://zentao.test"),
                    "apiBaseUrl": self.targets.get(request.url.host, "http://zentao.test")
                    + "/api.php/v2",
                }
            elif name == "get_projects":
                page = args["pageID"]
                values = range(1, 101) if page == 1 or self.mode == "repeat" else [101]
                data = {
                    "projects": [
                        {"id": str(i), "name": f"项目{i}", "deleted": "0"} for i in values
                    ],
                    "pager": {"recTotal": 101},
                }
            elif name == "get_projects_projectID_executions":
                assert str(args["projectID"]) == "101"
                data = {"executions": [{"id": "201", "name": "执行", "deleted": "0"}], "total": 1}
            elif name == "get_executions_executionID_stories":
                assert str(args["executionID"]) == "201"
                data = {
                    "stories": {
                        "301": {
                            "id": "301",
                            "title": "需求",
                            "deleted": "1" if self.mode == "deleted" else "0",
                        },
                        "302": {"id": "302", "title": "需求二"},
                    }
                }
            else:
                raise AssertionError(name)
            result = {"structuredContent": {"status": "success", **data}}
            if self.mode == "403" and name != "get_zentao_instance":
                result = {"content": [{"type": "text", "text": "HTTP 403"}]}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})


@pytest.fixture
def setup(api, monkeypatch):
    remote = Remote()
    monkeypatch.setattr(
        "testing_agent.services.zentao_mcp.McpClient",
        lambda url, token: McpClient(url, token, transport=httpx.MockTransport(remote.handle)),
    )
    monkeypatch.setattr(
        "testing_agent.services.zentao_mcp_instance.McpClient",
        lambda url, token: McpClient(url, token, transport=httpx.MockTransport(remote.handle)),
    )
    _, owner = account(api, "owner")
    pid = project(api, owner)
    sprint = make_sprint(api, owner, pid)
    req = make_requirement(api, owner, sprint)
    base = f"/v1/projects/{pid}/services/mcp"
    response = api.post(
        base,
        headers=owner,
        json={
            "name": "MCP",
            "baseUrl": "http://mcp.test/mcp",
            "zentaoInstanceUrl": "http://zentao.test",
            "templateId": "zentao",
        },
    )
    assert response.status_code == 200, response.text
    sid = response.json()["data"]["serviceId"]
    auth = f"{base}/{sid}/authorization"
    assert api.put(auth, headers=owner, json={"token": "owner-token"}).status_code == 200
    return {
        "owner": owner,
        "pid": pid,
        "sprint": sprint,
        "req": req,
        "auth": auth,
        "remote": remote,
    }


def bind(api, s, kind, identifier):
    path = {
        "project": f"projects/{s['pid']}",
        "sprint": f"sprints/{s['sprint']}",
        "requirement": f"requirements/{s['req']}",
    }[kind]
    return api.post(
        f"/v1/{path}/bindings",
        headers=s["owner"],
        json={
            "provider": "zentao",
            "remoteResourceId": str(identifier),
            "remoteNameSnapshot": "untrusted-name",
        },
    )


def bind_parents(api, s):
    assert bind(api, s, "project", 101).status_code == 200
    assert bind(api, s, "sprint", 201).status_code == 200


def test_all_pages_and_full_binding_chain_without_legacy_connection(api, setup):
    s = setup
    response = api.get(f"/v1/projects/{s['pid']}/zentao/mcp/projects", headers=s["owner"])
    assert response.status_code == 200, response.text
    assert response.json()["data"]["total"] == 101
    bind_parents(api, s)
    response = bind(api, s, "requirement", 301)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["remoteParentId"] == "201" and data["remoteNameSnapshot"] == "需求"
    assert data["instanceUrl"] == "http://zentao.test"
    assert bind(api, s, "requirement", 302).status_code == 409
    assert set(s["remote"].tokens) == {"owner-token"}
    project_calls = [a for n, a in s["remote"].calls if n == "get_projects"]
    assert any(a["pageID"] == 2 for a in project_calls)
    assert all(a["browseType"] == "all" for a in project_calls)


def test_old_binding_updates_without_original_connection_and_preserves_identity(api, setup):
    s = setup
    bind_parents(api, s)
    original = bind(api, s, "requirement", 301).json()["data"]

    async def make_legacy():
        async with api.app.state.test_sessions() as session:
            row = await session.scalar(
                select(ResourceBinding).where(ResourceBinding.binding_id == original["bindingId"])
            )
            row.connection_id = "deleted-legacy-connection"
            await session.commit()

    asyncio.run(make_legacy())
    url = f"/v1/requirements/{s['req']}/bindings/{original['bindingId']}"
    response = api.patch(url, headers=s["owner"], json={"remoteResourceId": "302"})
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert result["bindingId"] == original["bindingId"]
    assert result["connectionId"] == "deleted-legacy-connection"
    assert result["remoteResourceId"] == "302" and result["remoteNameSnapshot"] == "需求二"
    assert result["lastVerifiedAt"]


def test_parent_relation_deleted_and_unknown_targets_are_rejected(api, setup):
    s = setup
    assert bind(api, s, "sprint", 201).status_code == 400
    assert bind(api, s, "project", 999).status_code == 400
    bind_parents(api, s)
    assert bind(api, s, "requirement", 999).status_code == 400
    s["remote"].mode = "deleted"
    assert bind(api, s, "requirement", 301).status_code == 400
    assert bind(api, s, "requirement", 302).status_code == 200
    project_binding = api.get(f"/v1/projects/{s['pid']}/bindings", headers=s["owner"]).json()[
        "data"
    ]["items"][0]
    response = api.patch(
        f"/v1/projects/{s['pid']}/bindings/{project_binding['bindingId']}",
        headers=s["owner"],
        json={"remoteResourceId": "100"},
    )
    assert response.status_code == 400  # Existing child bindings protect the hierarchy.


def test_personal_authorization_and_roles(api, setup):
    s = setup
    s["remote"].tokens.clear()
    _, member = account(api, "member")
    assert (
        api.post(
            f"/v1/projects/{s['pid']}/members",
            headers=s["owner"],
            json={"name": "member", "role": "member"},
        ).status_code
        == 200
    )
    url = f"/v1/projects/{s['pid']}/zentao/mcp/projects"
    assert api.get(url, headers=member).status_code == 400
    assert s["remote"].calls == []
    assert api.put(s["auth"], headers=member, json={"token": "member-token"}).status_code == 200
    assert api.get(url, headers=member).status_code == 200
    assert set(s["remote"].tokens) == {"member-token"}
    assert (
        api.post(
            f"/v1/projects/{s['pid']}/bindings",
            headers=member,
            json={"provider": "zentao", "remoteResourceId": "101"},
        ).status_code
        == 403
    )
    _, outsider = account(api, "outsider")
    assert api.get(url, headers=outsider).status_code == 403
    assert api.delete(s["auth"], headers=member).status_code == 200
    assert api.get(url, headers=member).status_code == 400


@pytest.mark.parametrize("mode", ["403", "repeat"])
def test_remote_errors_do_not_persist_bindings(api, setup, mode):
    s = setup
    s["remote"].mode = mode
    response = bind(api, s, "project", 101)
    assert response.status_code >= 400
    listed = api.get(f"/v1/projects/{s['pid']}/bindings", headers=s["owner"]).json()["data"]
    assert listed["total"] == 0


def test_instance_mismatch_blocks_revalidation(api, setup):
    s = setup
    original = bind(api, s, "project", 101).json()["data"]

    async def old_instance():
        async with api.app.state.test_sessions() as session:
            row = await session.scalar(
                select(ResourceBinding).where(ResourceBinding.binding_id == original["bindingId"])
            )
            row.instance_url = "https://different.test"
            await session.commit()

    asyncio.run(old_instance())
    s["remote"].calls.clear()
    response = api.patch(
        f"/v1/projects/{s['pid']}/bindings/{original['bindingId']}", headers=s["owner"], json={}
    )
    assert response.status_code == 409
    assert s["remote"].calls == []


def add_mcp(api, s, token="second-token"):
    path = f"/v1/projects/{s['pid']}/services/mcp"
    response = api.post(
        path,
        headers=s["owner"],
        json={
            "name": "第二项 MCP",
            "templateId": "zentao",
            "baseUrl": "http://second-mcp.test/mcp",
        },
    )
    assert response.status_code == 200, response.text
    sid = response.json()["data"]["serviceId"]
    if token:
        response = api.put(f"{path}/{sid}/authorization", headers=s["owner"], json={"token": token})
        assert response.status_code == 200, response.text
    return sid


def test_project_selection_is_inherited_by_all_binding_levels(api, setup):
    s = setup
    sid = add_mcp(api, s)
    path = f"/v1/projects/{s['pid']}/bindings"
    assert bind(api, s, "project", 101).status_code == 400
    response = api.post(
        path,
        headers=s["owner"],
        json={
            "provider": "zentao",
            "remoteResourceId": "101",
            "mcpServiceId": sid,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["mcpServiceId"] == sid
    s["remote"].tokens.clear()
    assert bind(api, s, "sprint", 201).json()["data"]["mcpServiceId"] == sid
    assert bind(api, s, "requirement", 301).json()["data"]["mcpServiceId"] == sid
    response = api.get(f"/v1/projects/{s['pid']}/zentao/mcp/projects", headers=s["owner"])
    assert response.status_code == 200, response.text
    assert set(s["remote"].tokens) == {"second-token"}


def test_lower_bindings_cannot_override_project_mcp_even_on_same_instance(api, setup):
    s = setup
    bind_parents(api, s)
    sid = add_mcp(api, s)
    response = api.post(
        f"/v1/requirements/{s['req']}/bindings",
        headers=s["owner"],
        json={
            "provider": "zentao",
            "remoteResourceId": "301",
            "mcpServiceId": sid,
        },
    )
    assert response.status_code == 400, response.text
    assert bind(api, s, "requirement", 301).status_code == 200


def test_same_instance_project_mcp_change_preserves_and_updates_child_bindings(api, setup):
    s = setup
    root = bind(api, s, "project", 101).json()["data"]
    assert bind(api, s, "sprint", 201).status_code == 200
    leaf = bind(api, s, "requirement", 301).json()["data"]
    sid = add_mcp(api, s)
    response = api.patch(
        f"/v1/projects/{s['pid']}/bindings/{root['bindingId']}",
        headers=s["owner"],
        json={
            "remoteResourceId": "101",
            "mcpServiceId": sid,
        },
    )
    assert response.status_code == 200, response.text
    result = api.get(f"/v1/requirements/{s['req']}/bindings", headers=s["owner"]).json()["data"][
        "items"
    ][0]
    assert result["bindingId"] == leaf["bindingId"] and result["remoteResourceId"] == "301"
    assert result["mcpServiceId"] == sid
    s["remote"].tokens.clear()
    response = api.patch(
        f"/v1/requirements/{s['req']}/bindings/{leaf['bindingId']}",
        headers=s["owner"],
        json={"remoteResourceId": "302"},
    )
    assert response.status_code == 200, response.text
    assert set(s["remote"].tokens) == {"second-token"}


def test_selected_mcp_requires_own_authorization_and_never_falls_back(api, setup):
    s = setup
    root = bind(api, s, "project", 101).json()["data"]
    sid = add_mcp(api, s, token="")
    response = api.patch(
        f"/v1/projects/{s['pid']}/bindings/{root['bindingId']}",
        headers=s["owner"],
        json={"remoteResourceId": "101", "mcpServiceId": sid},
    )
    assert response.status_code == 400
    assert (
        api.get(f"/v1/projects/{s['pid']}/bindings", headers=s["owner"]).json()["data"]["items"][0][
            "mcpServiceId"
        ]
        == root["mcpServiceId"]
    )
    assert (
        api.delete(
            f"/v1/projects/{s['pid']}/services/mcp/{root['mcpServiceId']}", headers=s["owner"]
        ).status_code
        == 200
    )
    assert (
        api.get(f"/v1/projects/{s['pid']}/zentao/mcp/projects", headers=s["owner"]).status_code
        == 400
    )


def test_second_instance_is_independent_and_project_rebind_requires_confirmation(api, setup):
    s = setup
    root = bind(api, s, "project", 101).json()["data"]
    assert bind(api, s, "sprint", 201).status_code == 200
    assert bind(api, s, "requirement", 301).status_code == 200
    s["remote"].targets["second-mcp.test"] = "http://other-zentao.test"
    sid = add_mcp(api, s)
    # Another service must not inherit the first service's historical identity restriction.
    candidates = api.get(
        f"/v1/projects/{s['pid']}/zentao/mcp/projects",
        headers=s["owner"],
        params={"mcpServiceId": sid},
    )
    assert candidates.status_code == 200, candidates.text
    path = f"/v1/projects/{s['pid']}/bindings/{root['bindingId']}"
    body = {"remoteResourceId": "101", "mcpServiceId": sid}
    assert api.patch(path, headers=s["owner"], json=body).status_code == 400
    assert (
        api.get(f"/v1/sprints/{s['sprint']}/bindings", headers=s["owner"]).json()["data"]["total"]
        == 1
    )
    response = api.patch(path, headers=s["owner"], json={**body, "confirmInstanceSwitch": True})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["instanceUrl"] == "http://other-zentao.test"
    assert response.json()["data"]["mcpServiceId"] == sid
    assert (
        api.get(f"/v1/sprints/{s['sprint']}/bindings", headers=s["owner"]).json()["data"]["total"]
        == 0
    )
    assert (
        api.get(f"/v1/requirements/{s['req']}/bindings", headers=s["owner"]).json()["data"]["total"]
        == 0
    )


def test_editing_unused_mcp_target_preserves_the_selected_projects_bindings(api, setup):
    s = setup
    root = bind(api, s, "project", 101).json()["data"]
    assert bind(api, s, "sprint", 201).status_code == 200
    assert bind(api, s, "requirement", 301).status_code == 200
    sid = add_mcp(api, s)
    s["remote"].targets["second-mcp.test"] = "http://another-target.test"
    response = api.patch(
        f"/v1/projects/{s['pid']}/services/mcp/{sid}",
        headers=s["owner"],
        json={
            "name": "第二项 MCP",
            "baseUrl": "http://second-mcp.test/mcp",
            "confirmInstanceSwitch": True,
        },
    )
    assert response.status_code == 200, response.text
    saved = api.get(f"/v1/projects/{s['pid']}/bindings", headers=s["owner"]).json()["data"][
        "items"
    ][0]
    assert saved["bindingId"] == root["bindingId"] and saved["mcpServiceId"] == root["mcpServiceId"]
    assert (
        api.get(f"/v1/requirements/{s['req']}/bindings", headers=s["owner"]).json()["data"]["total"]
        == 1
    )
    assert (
        api.get(f"/v1/projects/{s['pid']}/zentao/mcp/projects", headers=s["owner"]).status_code
        == 200
    )
