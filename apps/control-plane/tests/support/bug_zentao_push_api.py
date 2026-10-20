"""Shared preparation for bug zentao push api tests; no collected cases."""

import asyncio
import threading

import httpx
import pytest
from integration_test_driver import enable
from sqlalchemy import select

from support.bug_api import create_bug
from support.function_case_library import make_requirement, make_sprint
from support.project_api import account, project
from support.project_api import api as api
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.services.mcp_client import McpClient
from testing_agent.services.service_instance import instance_key


@pytest.fixture(autouse=True)
def migration_mode(api):
    enable(api)


INSTANCE = "http://zentao.test"


class Remote:
    def __init__(self):
        self.calls = []
        self.headers = []
        self.endpoints = []
        self.instance = INSTANCE
        self.failure = ""
        self.project_id = 10
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block = False
        self.on_verify = None
        self.builds = [
            {"id": "60", "name": "v1.0", "project": "10", "execution": "20", "product": "40"}
        ]
        self.users = [{"id": "1", "account": "dev", "realname": "开发甲", "type": "inside"}]
        self.build_pages = None
        self.user_pages = None
        self.paging_supported = True

    async def handle(self, request):
        import json

        body = json.loads(request.content)
        self.headers.append(request.headers.get("token"))
        self.endpoints.append(str(request.url))
        method = body["method"]
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "initialize":
            result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}}
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "get_executions_executionID_builds",
                        "inputSchema": {
                            "properties": {
                                key: {} for key in ("executionID", "pageID", "recPerPage")
                            }
                            if self.paging_supported
                            else {},
                        },
                    }
                ]
            }
        else:
            name = body["params"]["name"]
            arguments = body["params"]["arguments"]
            if name != "get_zentao_instance":
                self.calls.append((name, arguments))
            if name == "get_stories_storyID" and self.on_verify:
                await self.on_verify()
            data = {
                "get_zentao_instance": {
                    "schemaVersion": 1,
                    "instanceUrl": self.instance,
                    "apiBaseUrl": self.instance + "/api.php/v2",
                },
                "get_projects": {"projects": [{"id": 10, "name": "项目"}], "total": 1},
                "get_executions_executionID": {"execution": {"id": 20, "project": self.project_id}},
                "get_stories_storyID": {"story": {"id": 30, "product": 40}},
                "get_executions_executionID_stories": {"stories": [{"id": "30"}]},
                "get_bugs_bugID": {
                    "bug": {
                        "id": 50,
                        "title": "登录失败",
                        "project": 10,
                        "execution": 20,
                        "story": 30,
                        "product": 40,
                    }
                },
                "post_bugs": {"status": "success", "id": 50},
                "get_executions_executionID_builds": self.build_pages.get(
                    arguments.get("pageID", 1), {"builds": []}
                )
                if self.build_pages is not None
                else {"builds": self.builds, "total": len({b["id"] for b in self.builds})},
                "get_users": self.user_pages.get(arguments.get("pageID", 1), {"users": []})
                if self.user_pages is not None
                else {"users": self.users, "total": len(self.users)},
            }[name]
            if name == "post_bugs":
                self.entered.set()
                if self.block:
                    while not self.release.is_set():
                        await asyncio.sleep(0.01)
                if self.failure == "timeout":
                    raise httpx.ReadTimeout("secret-must-not-leak", request=request)
                if self.failure == "403":
                    result = {
                        "content": [
                            {"type": "text", "text": "HTTP 403"},
                            {"type": "text", "text": '{"error":"Access denied"}'},
                        ]
                    }
                    return httpx.Response(
                        200, json={"jsonrpc": "2.0", "id": body["id"], "result": result}
                    )
                if self.failure == "missing-id":
                    data = {"status": "success"}
                if self.failure == "missing-status":
                    data = {"id": 50}
            result = {"structuredContent": data}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    @property
    def writes(self):
        return [arguments for name, arguments in self.calls if name == "post_bugs"]


@pytest.fixture
def setup(api, monkeypatch):
    remote = Remote()
    monkeypatch.setattr(
        "testing_agent.services.zentao_mcp_instance.McpClient",
        lambda url, token: McpClient(url, token, transport=httpx.MockTransport(remote.handle)),
    )
    monkeypatch.setattr(
        "testing_agent.services.bug_zentao_push.McpClient",
        lambda url, token: McpClient(url, token, transport=httpx.MockTransport(remote.handle)),
    )
    user, owner = account(api, "owner")
    pid = project(api, owner)
    sprint = make_sprint(api, owner, pid)
    req = make_requirement(api, owner, sprint)
    bug = create_bug(api, owner, pid, sprint, reporter=user, requirementId=req)
    path = f"/v1/projects/{pid}/services/mcp"
    response = api.post(
        path,
        headers=owner,
        json={
            "name": "禅道 MCP",
            "baseUrl": "http://mcp.test/zentao/mcp",
            "templateId": "zentao",
            "zentaoInstanceUrl": INSTANCE,
        },
    )
    assert response.status_code == 200, response.text
    sid = response.json()["data"]["serviceId"]
    assert (
        api.put(
            f"{path}/{sid}/authorization", headers=owner, json={"token": "owner-secret"}
        ).status_code
        == 200
    )

    async def seed():
        async with api.app.state.test_sessions() as session:
            for kind, local_id, remote_kind, remote_id, parent in (
                ("project", pid, "project", "10", ""),
                ("sprint", sprint, "execution", "20", "10"),
                ("requirement", req, "story", "30", "20"),
            ):
                session.add(
                    ResourceBinding(
                        binding_id=f"{kind}-binding",
                        user_id=user["userId"],
                        provider="zentao",
                        instance_url=INSTANCE,
                        instance_key=instance_key(INSTANCE),
                        connection_id="original-zentao-connection",
                        local_resource_type=kind,
                        local_resource_id=local_id,
                        remote_resource_type=remote_kind,
                        remote_resource_id=remote_id,
                        remote_parent_id=parent,
                        remote_name_snapshot=f"remote-{kind}",
                        status="active",
                    )
                )
            await session.commit()

    asyncio.run(seed())
    return {
        "owner": owner,
        "pid": pid,
        "bug": bug,
        "remote": remote,
        "sid": sid,
        "path": path,
        "url": f"/v1/bugs/{bug['bugId']}/zentao-push",
    }


def change(api, model, field, value, **where):
    async def mutate():
        async with api.app.state.test_sessions() as session:
            row = await session.scalar(select(model).filter_by(**where))
            setattr(row, field, value)
            await session.commit()

    asyncio.run(mutate())
