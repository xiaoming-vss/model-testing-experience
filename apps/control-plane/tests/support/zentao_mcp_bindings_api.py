"""Shared preparation for zentao mcp bindings api tests; no collected cases."""

import json

import httpx
import pytest

from support.function_case_library import make_requirement, make_sprint
from support.project_api import account, project
from support.project_api import api as api
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
