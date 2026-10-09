"""禅道新建 Bug 导入：真实鉴权/数据库/HTTP，仅替换 MCP 传输（MockTransport）。"""

import asyncio
import json

import httpx
import pytest
from integration_test_driver import enable
from sqlalchemy import select
from test_bug_api import create_bug
from test_bug_zentao_push_api import INSTANCE
from test_function_case_library import make_requirement, make_sprint
from test_project_membership_api import account, project
from test_project_membership_api import api as api

from testing_agent.models.bug_activity import BugActivity
from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.models.bug_zentao_sync_baseline import BugZentaoSyncBaseline
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.services.mcp_client import McpClient
from testing_agent.services.service_instance import instance_key


@pytest.fixture(autouse=True)
def migration_mode(api):
    enable(api)


def remote_bug(number, **overrides):
    detail = {
        "id": number,
        "title": f"禅道缺陷 {number}",
        "severity": "1",
        "pri": "3",
        "status": "active",
        "confirmed": "0",
        "resolution": "",
        "resolvedBuild": "",
        "duplicateBug": "",
        "activatedCount": "0",
        "execution": 20,
        "story": 30,
        "assignedTo": "dev",
        "openedBy": "tester",
        "openedDate": "2026-10-01 10:00:00",
        "deleted": "0",
        "steps": "<p>复现步骤</p>",
        "product": 40,
        "project": 10,
    }
    detail.update(overrides)
    return detail


class Remote:
    def __init__(self, details):
        self.details = {int(key): value for key, value in details.items()}
        self.instance = INSTANCE
        self.calls = []
        self.tokens = []

    async def handle(self, request):
        body = json.loads(request.content)
        self.tokens.append(request.headers.get("token"))
        method = body["method"]
        if method == "notifications/initialized":
            return httpx.Response(202)

        def reply(result):
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

        if method == "initialize":
            return reply({"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}})
        if method == "tools/list":
            return reply({"tools": []})
        name = body["params"]["name"]
        arguments = body["params"]["arguments"]
        self.calls.append((name, arguments))
        if name == "get_zentao_instance":
            data = {
                "schemaVersion": 1,
                "instanceUrl": self.instance,
                "apiBaseUrl": self.instance + "/api.php/v2",
            }
        elif name == "get_projects_projectID_bugs":
            rows = [
                {
                    "id": key,
                    "title": value["title"],
                    "status": value["status"],
                    "severity": value["severity"],
                    "pri": value["pri"],
                    "assignedTo": value["assignedTo"],
                    "openedBy": value["openedBy"],
                    "openedDate": value["openedDate"],
                    "execution": value["execution"],
                    "story": value["story"],
                    "deleted": value["deleted"],
                }
                for key, value in self.details.items()
            ]
            data = {"bugs": rows, "total": len(rows)}
        elif name == "get_bugs_bugID":
            data = {"bug": self.details[int(arguments["bugID"])]}
        else:
            raise AssertionError(f"unexpected tool {name}")
        return reply({"structuredContent": data})


@pytest.fixture
def setup(api, monkeypatch):
    remote = Remote(
        {
            50: remote_bug(50),
            51: remote_bug(51, pri="2", status="resolved", resolution="fixed", resolvedBuild="v2"),
            52: remote_bug(52, steps="<p>截图</p><img src='http://zentao/file/1.png'/>"),
            53: remote_bug(53, status="custom"),
            54: remote_bug(54, severity=""),
        }
    )
    transport = httpx.MockTransport(remote.handle)
    monkeypatch.setattr(
        "testing_agent.services.zentao_mcp_instance.McpClient",
        lambda url, token: McpClient(url, token, transport=transport),
    )
    # ZentaoMcpAccess.resolve 从 zentao_mcp 命名空间取 McpClient 传入 discover_instance。
    monkeypatch.setattr(
        "testing_agent.services.zentao_mcp.McpClient",
        lambda url, token: McpClient(url, token, transport=transport),
    )
    monkeypatch.setattr(
        "testing_agent.services.zentao_bug_import.McpClient",
        lambda url, token: McpClient(url, token, transport=transport),
    )
    owner_user, owner = account(api, "owner")
    pid = project(api, owner)
    sprint = make_sprint(api, owner, pid)
    req = make_requirement(api, owner, sprint)
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
            session.add_all(
                [
                    ResourceBinding(
                        binding_id="project-binding",
                        user_id="seed",
                        provider="zentao",
                        instance_url=INSTANCE,
                        instance_key=instance_key(INSTANCE),
                        connection_id="original-zentao-connection",
                        local_resource_type="project",
                        local_resource_id=pid,
                        remote_resource_type="project",
                        remote_resource_id="10",
                        remote_parent_id="",
                        remote_name_snapshot="remote-project",
                        status="active",
                    ),
                    ResourceBinding(
                        binding_id="sprint-binding",
                        user_id="seed",
                        provider="zentao",
                        instance_url=INSTANCE,
                        instance_key=instance_key(INSTANCE),
                        connection_id="original-zentao-connection",
                        local_resource_type="sprint",
                        local_resource_id=sprint,
                        remote_resource_type="execution",
                        remote_resource_id="20",
                        remote_parent_id="10",
                        remote_name_snapshot="remote-execution",
                        status="active",
                    ),
                    ResourceBinding(
                        binding_id="requirement-binding",
                        user_id="seed",
                        provider="zentao",
                        instance_url=INSTANCE,
                        instance_key=instance_key(INSTANCE),
                        connection_id="original-zentao-connection",
                        local_resource_type="requirement",
                        local_resource_id=req,
                        remote_resource_type="story",
                        remote_resource_id="30",
                        remote_parent_id="20",
                        remote_name_snapshot="remote-story",
                        status="active",
                    ),
                ]
            )
            await session.commit()

    asyncio.run(seed())
    return {
        "owner": owner,
        "owner_user": owner_user,
        "owner_id": owner_user["userId"],
        "pid": pid,
        "sprint": sprint,
        "req": req,
        "remote": remote,
        "candidates": f"/v1/projects/{pid}/zentao/bug-imports/candidates",
        "preview": f"/v1/projects/{pid}/zentao/bug-imports/preview",
        "import": f"/v1/projects/{pid}/zentao/bug-imports",
    }


def import_item(sprint_id, number, assignee, **overrides):
    body = {
        "remoteBugId": number,
        "assigneeUserId": assignee,
        "foundSprintId": sprint_id,
    }
    body.update(overrides)
    return body


def test_candidates_mark_linked_filter_and_paginate(api, setup):
    field = setup
    owner = field["owner"]
    bug = create_bug(api, owner, field["pid"], field["sprint"], reporter=field["owner_user"])

    async def seed_link():
        async with api.app.state.test_sessions() as session:
            session.add(
                BugZentaoPush(
                    bug_id=bug["bugId"],
                    source="push",
                    operation_id="op-linked",
                    actor_user_id="owner",
                    service_id="svc",
                    instance_url=INSTANCE,
                    instance_key=instance_key(INSTANCE),
                    status="succeeded",
                    remote_bug_id=50,
                    target_json={},
                    payload_json={},
                )
            )
            await session.commit()
            return bug

    asyncio.run(seed_link())
    body = api.get(field["candidates"], headers=owner).json()
    assert body["code"] == 0, body
    data = body["data"]
    assert data["total"] == 5
    linked = {item["remoteBugId"]: item["linked"] for item in data["items"]}
    assert linked[50] is True
    assert linked[51] is False

    data = api.get(field["candidates"], headers=owner, params={"status": "resolved"}).json()["data"]
    assert [item["remoteBugId"] for item in data["items"]] == [51]

    data = api.get(field["candidates"], headers=owner, params={"keyword": "缺陷 51"}).json()["data"]
    assert [item["remoteBugId"] for item in data["items"]] == [51]

    data = api.get(field["candidates"], headers=owner, params={"pageSize": 2, "page": 2}).json()[
        "data"
    ]
    assert data["total"] == 5 and len(data["items"]) == 2


def test_preview_maps_bindings_and_reports_pending(api, setup):
    field = setup
    owner = field["owner"]
    data = api.post(
        field["preview"], headers=owner, json={"remoteBugIds": [50, 51, 52, 53, 54]}
    ).json()["data"]["items"]
    by_id = {item["remoteBugId"]: item for item in data}

    ready = by_id[50]
    assert ready["state"] == "ready"
    assert ready["converted"]["severity"] == "fatal"
    assert ready["converted"]["priority"] == "medium"
    assert ready["converted"]["status"] == "active"
    assert ready["converted"]["foundSprintId"] == field["sprint"]
    assert ready["converted"]["requirementId"] == field["req"]
    assert {"field": "assigneeUserId", "reason": ready["pending"][0]["reason"]} in ready["pending"]

    manual = by_id[51]
    assert manual["state"] == "ready"
    # 优先级 2 现已无损映射为平台「高」，不再进入待映射清单。
    assert manual["converted"]["priority"] == "high"
    assert [item["field"] for item in manual["pending"]] == ["assigneeUserId"]
    assert manual["converted"]["status"] == "resolved"
    assert manual["converted"]["resolvedBuild"] == "v2"

    assert by_id[52]["state"] == "pending_files"
    assert by_id[53]["state"] == "pending"
    assert by_id[54]["state"] == "ready"
    assert by_id[54]["converted"]["severity"] is None


def test_import_creates_linked_bug_with_baselines_and_activity(api, setup):
    field = setup
    owner = field["owner"]
    response = api.post(
        field["import"],
        headers=owner,
        json={
            "requestId": "req-20261009-0001",
            "items": [
                import_item(
                    field["sprint"],
                    51,
                    field["owner_id"],
                    requirementId=field["req"],
                    priority="high",
                )
            ],
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()["data"]["items"][0]
    assert result["status"] == "success"
    assert result["bugNo"] > 0

    async def load():
        async with api.app.state.test_sessions() as session:
            push = await session.scalar(
                select(BugZentaoPush).where(BugZentaoPush.remote_bug_id == 51)
            )
            baselines = (
                await session.scalars(
                    select(BugZentaoSyncBaseline).where(BugZentaoSyncBaseline.bug_id == push.bug_id)
                )
            ).all()
            activities = (
                await session.scalars(select(BugActivity).where(BugActivity.bug_id == push.bug_id))
            ).all()
            return push, baselines, activities

    push, baselines, activities = asyncio.run(load())
    assert push.source == "import"
    assert push.status == "succeeded"
    assert push.operation_id == "req-20261009-0001:51"
    assert push.instance_key == instance_key(INSTANCE)
    assert push.payload_json == {}
    assert push.source_json["openedBy"] == "tester"
    assert {baseline.field_group for baseline in baselines} == {
        "profile",
        "description",
        "status",
        "assignee",
    }
    status_baseline = next(b for b in baselines if b.field_group == "status")
    assert status_baseline.remote_snapshot_json == {
        "status": "resolved",
        "confirmed": False,
        "resolution": "fixed",
        "resolvedBuild": "v2",
        "activatedCount": 0,
    }
    assert {activity.action for activity in activities} >= {"create", "zentao_import"}
    sync_activity = next(a for a in activities if a.action == "zentao_import")
    assert sync_activity.kind == "sync"

    detail = api.get(f"/v1/bugs/{result['bugId']}", headers=owner).json()["data"]
    assert detail["status"] == "resolved"
    assert detail["confirmed"] is False
    assert detail["resolution"] == "fixed"
    assert detail["resolvedBuild"] == "v2"
    assert detail["severity"] == "fatal"
    assert detail["priority"] == "high"
    assert detail["descriptionHtml"] == "<p>复现步骤</p>"

    status_response = api.get(f"/v1/bugs/{result['bugId']}/zentao-push", headers=owner).json()[
        "data"
    ]
    assert status_response["status"] == "succeeded"
    assert status_response["source"] == "import"
    assert status_response["remoteBugId"] == 51


def test_import_is_idempotent_and_deduplicates(api, setup):
    field = setup
    owner = field["owner"]
    body = {
        "requestId": "req-20261009-0002",
        "items": [
            import_item(field["sprint"], 50, field["owner_id"]),
            import_item(field["sprint"], 50, field["owner_id"]),
        ],
    }
    first = api.post(field["import"], headers=owner, json=body).json()["data"]["items"]
    assert first[0]["status"] == "success"
    assert first[1]["status"] == "failed"
    assert "重复" in first[1]["errorMessage"]

    replay = api.post(field["import"], headers=owner, json=body).json()["data"]["items"]
    assert replay[0]["status"] == "success"
    assert replay[0]["bugId"] == first[0]["bugId"]

    rerun = api.post(
        field["import"],
        headers=owner,
        json={
            "requestId": "req-20261009-0003",
            "items": [import_item(field["sprint"], 50, field["owner_id"])],
        },
    ).json()["data"]["items"]
    assert rerun[0]["status"] == "already_linked"
    assert rerun[0]["bugId"] == first[0]["bugId"]


def test_import_rejects_invalid_selections_and_unmappable_status(api, setup):
    field = setup
    owner = field["owner"]
    results = api.post(
        field["import"],
        headers=owner,
        json={
            "requestId": "req-20261009-0004",
            "items": [
                import_item(field["sprint"], 50, "stranger"),
                import_item("no-such-sprint", 51, field["owner_id"], priority="high"),
                import_item(field["sprint"], 53, field["owner_id"]),
                import_item(field["sprint"], 52, field["owner_id"]),
            ],
        },
    ).json()["data"]["items"]
    assert [item["status"] for item in results] == ["failed", "failed", "failed", "pending"]
    assert "可指派的成员" in results[0]["errorMessage"]
    assert "发现迭代" in results[1]["errorMessage"]
    assert "无法映射" in results[2]["errorMessage"]
    assert "图片" in results[3]["errorMessage"]


def test_viewer_and_developer_cannot_import(api, setup):
    field = setup
    owner, pid = field["owner"], field["pid"]
    _, viewer = account(api, "viewer")
    api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "viewer", "role": "viewer"}
    )
    assert api.get(field["candidates"], headers=viewer).status_code == 403
    assert (
        api.post(field["preview"], headers=viewer, json={"remoteBugIds": [50]}).status_code == 403
    )
