"""已关联 Bug 从禅道拉取更新：基线三方比对、冲突选择与过期预览防护。"""

import asyncio
import json

import httpx
import pytest
from integration_test_driver import enable
from sqlalchemy import select
from support.bug_zentao_push_api import INSTANCE
from support.function_case_library import make_sprint
from support.project_api import account, project
from support.project_api import api as api

from testing_agent.models.bug import Bug
from testing_agent.models.bug_activity import BugActivity
from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.models.bug_zentao_sync_baseline import BugZentaoSyncBaseline
from testing_agent.services.mcp_client import McpClient
from testing_agent.services.service_instance import instance_key


@pytest.fixture(autouse=True)
def migration_mode(api):
    enable(api)


def remote_detail(number=50, **overrides):
    detail = {
        "id": number,
        "title": "登录失败",
        "severity": "2",
        "pri": "4",
        "status": "active",
        "confirmed": "1",
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
        "steps": "<p>远端正文</p>",
        "product": 40,
        "project": 10,
    }
    detail.update(overrides)
    return detail


class Remote:
    def __init__(self):
        self.detail = remote_detail()
        self.instance = INSTANCE
        self.calls = []
        self.deleted = False

    async def handle(self, request):
        body = json.loads(request.content)
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
        if name == "get_zentao_instance":
            return reply(
                {
                    "structuredContent": {
                        "schemaVersion": 1,
                        "instanceUrl": self.instance,
                        "apiBaseUrl": self.instance + "/api.php/v2",
                    }
                }
            )
        if name == "get_bugs_bugID":
            if self.deleted:
                detail = dict(self.detail, deleted="1")
            else:
                detail = self.detail
            return reply({"structuredContent": {"bug": detail}})
        raise AssertionError(f"unexpected tool {name}")


@pytest.fixture
def setup(api, monkeypatch):
    remote = Remote()
    transport = httpx.MockTransport(remote.handle)
    for target in (
        "testing_agent.services.zentao_mcp_instance.McpClient",
        "testing_agent.services.zentao_mcp.McpClient",
        "testing_agent.services.bug_zentao_pull.McpClient",
    ):
        monkeypatch.setattr(
            target,
            lambda url, token: McpClient(url, token, transport=transport),
        )
    owner_user, owner = account(api, "owner")
    pid = project(api, owner)
    sprint = make_sprint(api, owner, pid)
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
    bug = create_linked_bug(api, owner_user, owner, pid, sprint)
    return {
        "owner": owner,
        "owner_id": owner_user["userId"],
        "pid": pid,
        "sprint": sprint,
        "remote": remote,
        "bug": bug,
        "preview_url": f"/v1/bugs/{bug['bugId']}/zentao-remote",
        "pull_url": f"/v1/bugs/{bug['bugId']}/zentao-pull",
    }


def create_linked_bug(api, owner_user, owner, pid, sprint):
    """本地创建 Bug 并手工落一条推送关联，模拟「已推送成功」的存量数据。"""
    creation = api.post(
        f"/v1/projects/{pid}/bugs",
        headers=owner,
        json={
            "title": "登录失败",
            "descriptionHtml": "<p>本地正文</p>",
            "severity": "serious",
            "priority": "medium",
            "assigneeUserId": owner_user["userId"],
            "foundSprintId": sprint,
        },
    )
    assert creation.status_code == 200, creation.text
    bug = creation.json()["data"]

    async def seed():
        async with api.app.state.test_sessions() as session:
            session.add(
                BugZentaoPush(
                    bug_id=bug["bugId"],
                    source="push",
                    operation_id="op-seed",
                    actor_user_id=owner_user["userId"],
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

    asyncio.run(seed())
    return {**bug, "ownerId": owner_user["userId"]}


def preview(api, field):
    body = api.get(field["preview_url"], headers=field["owner"]).json()
    assert body["code"] == 0, body
    return body["data"]


def group(data, name):
    return next(item for item in data["groups"] if item["group"] == name)


def test_preview_compares_against_missing_baseline(api, setup):
    field = setup
    data = preview(api, field)
    assert data["remoteBugId"] == 50
    assert data["linkedSource"] == "push"

    profile = group(data, "profile")
    assert profile["state"] == "confirm_baseline"
    assert profile["local"] == {
        "title": "登录失败",
        "severity": "serious",
        "priority": "medium",
    }
    assert profile["remote"] == {
        "title": "登录失败",
        "severity": "serious",
        "priority": "low",
    }

    description = group(data, "description")
    assert description["state"] == "confirm_baseline"

    status = group(data, "status")
    assert status["state"] == "confirm_baseline"
    assert status["remote"]["confirmed"] is True

    assignee = group(data, "assignee")
    assert assignee["state"] == "manual"
    assert assignee["remote"] == {"account": "dev"}


def test_apply_remote_updates_bug_and_writes_baseline(api, setup):
    field = setup
    data = preview(api, field)
    response = api.post(
        field["pull_url"],
        headers=field["owner"],
        json={
            "remoteDigest": data["remoteDigest"],
            "groups": [
                {"group": "profile", "action": "apply_remote"},
                {"group": "status", "action": "apply_remote"},
                {
                    "group": "assignee",
                    "action": "apply_remote",
                    "assigneeUserId": field["owner_id"],
                },
                {"group": "description", "action": "keep_local"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert sorted(result["applied"]) == ["assignee", "profile", "status"]
    assert result["kept"] == ["description"]

    detail = api.get(f"/v1/bugs/{field['bug']['bugId']}", headers=field["owner"]).json()["data"]
    assert detail["severity"] == "serious"
    assert detail["priority"] == "low"
    assert detail["confirmed"] is True
    assert detail["assigneeUserId"] == field["owner_id"]
    assert detail["descriptionHtml"] == "<p>本地正文</p>"

    async def load():
        async with api.app.state.test_sessions() as session:
            bug = await session.scalar(select(Bug).where(Bug.bug_id == field["bug"]["bugId"]))
            baselines = (
                await session.scalars(
                    select(BugZentaoSyncBaseline).where(BugZentaoSyncBaseline.bug_id == bug.bug_id)
                )
            ).all()
            activities = (
                await session.scalars(select(BugActivity).where(BugActivity.bug_id == bug.bug_id))
            ).all()
            return bug, baselines, activities

    bug, baselines, activities = asyncio.run(load())
    assert {baseline.field_group for baseline in baselines} == {
        "profile",
        "description",
        "status",
        "assignee",
    }
    status_baseline = next(b for b in baselines if b.field_group == "status")
    assert status_baseline.remote_snapshot_json["confirmed"] is True
    # 保留的 description 基线：本地=本地当前值，远端=本轮远端值，二者不同（本地领先）。
    description_baseline = next(b for b in baselines if b.field_group == "description")
    assert description_baseline.local_snapshot_json != description_baseline.remote_snapshot_json
    sync_activity = next(a for a in activities if a.action == "zentao_pull")
    assert sync_activity.kind == "sync"
    assert sync_activity.detail_json["applied"] == result["applied"]

    # 第二次预览：已应用与保留确认过的组均为 synced（两端自我确认后未再变化）。
    again = preview(api, field)
    assert group(again, "profile")["state"] == "synced"
    assert group(again, "status")["state"] == "synced"
    assert group(again, "assignee")["state"] == "manual"
    assert group(again, "description")["state"] == "synced"


def test_conflict_requires_explicit_choice_and_stale_digest_rejected(api, setup):
    field = setup
    first = preview(api, field)
    # 建立基线（保留平台值），随后远端继续变化，本地也变化 → 冲突。
    response = api.post(
        field["pull_url"],
        headers=field["owner"],
        json={
            "remoteDigest": first["remoteDigest"],
            "groups": [{"group": "profile", "action": "keep_local"}],
        },
    )
    assert response.status_code == 200, response.text

    # 基线建立后，本地编辑标题，同时远端也变化 → 冲突。
    patched = api.patch(
        f"/v1/bugs/{field['bug']['bugId']}",
        headers=field["owner"],
        json={"title": "本地新标题"},
    )
    assert patched.status_code == 200, patched.text
    field["remote"].detail = remote_detail(title="远端新标题", pri="1")
    changed = preview(api, field)
    profile = group(changed, "profile")
    assert profile["state"] == "conflict"

    stale = api.post(
        field["pull_url"],
        headers=field["owner"],
        json={
            "remoteDigest": first["remoteDigest"],
            "groups": [{"group": "profile", "action": "apply_remote"}],
        },
    )
    assert stale.status_code == 409
    assert "重新预览" in stale.json()["message"]

    resolution = api.post(
        field["pull_url"],
        headers=field["owner"],
        json={
            "remoteDigest": changed["remoteDigest"],
            "groups": [{"group": "profile", "action": "keep_local"}],
        },
    )
    assert resolution.status_code == 200, resolution.text
    detail = api.get(f"/v1/bugs/{field['bug']['bugId']}", headers=field["owner"]).json()["data"]
    assert detail["title"] == "本地新标题"
    assert detail["priority"] == "medium"


def test_remote_deleted_stops_apply_and_local_data_kept(api, setup):
    field = setup
    field["remote"].deleted = True
    response = api.get(field["preview_url"], headers=field["owner"])
    assert response.status_code == 400
    assert "已删除" in response.json()["message"]
    detail = api.get(f"/v1/bugs/{field['bug']['bugId']}", headers=field["owner"]).json()["data"]
    assert detail["title"] == "登录失败"


def test_linked_bug_is_required_and_write_permission_enforced(api, setup):
    field = setup
    _, viewer = account(api, "viewer")
    api.post(
        f"/v1/projects/{field['pid']}/members",
        headers=field["owner"],
        json={"name": "viewer", "role": "viewer"},
    )
    assert api.get(field["preview_url"], headers=viewer).status_code == 403

    creation = api.post(
        f"/v1/projects/{field['pid']}/bugs",
        headers=field["owner"],
        json={
            "title": "未关联",
            "descriptionHtml": "<p>正文</p>",
            "severity": "normal",
            "priority": "medium",
            "assigneeUserId": field["owner_id"],
            "foundSprintId": field["sprint"],
        },
    )
    orphan = f"/v1/bugs/{creation.json()['data']['bugId']}/zentao-remote"
    response = api.get(orphan, headers=field["owner"])
    assert response.status_code == 409
    assert "尚未关联" in response.json()["message"]
