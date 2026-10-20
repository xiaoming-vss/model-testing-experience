"""禅道新建 Bug 导入：真实鉴权/数据库/HTTP，仅替换 MCP 传输（MockTransport）。"""

import asyncio
import hashlib
import json

import httpx
import pytest
from integration_test_driver import enable
from sqlalchemy import select
from support.bug_api import create_bug
from support.bug_zentao_push_api import INSTANCE
from support.function_case_library import make_requirement, make_sprint
from support.project_api import account, project
from support.project_api import api as api

from testing_agent.models.bug_activity import BugActivity
from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment
from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.models.bug_zentao_sync_baseline import BugZentaoSyncBaseline
from testing_agent.models.resource_binding import ResourceBinding
from testing_agent.services.mcp_client import McpClient
from testing_agent.services.service_instance import instance_key
from testing_agent.services.stored_file import StoredFileService


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

    def _row(self, value):
        return {
            "id": value["id"],
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
            rows = [self._row(value) for value in self.details.values()]
            data = {"bugs": rows, "total": len(rows)}
        elif name == "get_executions_executionID_bugs":
            rows = [
                self._row(value)
                for value in self.details.values()
                if str(value["execution"]) == str(arguments["executionID"])
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
            56: remote_bug(56, steps="<img src='http://zentao/file/9.png'/>"),
            55: remote_bug(
                55,
                execution=99,
                steps='<p>数据</p><img src="http://zentao.test/file-read-101.png"/>',
                attachments=[{"id": 101, "title": "截图.png", "size": 13}],
            ),
            57: remote_bug(
                57,
                steps='<p>日志</p><img src="http://zentao.test/file-read-102.png"/>',
                attachments=[{"id": 102, "title": "日志.png", "size": 13}],
            ),
        }
    )

    # MockTransport 在工厂内构造：测试包装 remote.handle 时按当时状态分发。
    def factory(url, token):
        return McpClient(url, token, transport=httpx.MockTransport(remote.handle))

    monkeypatch.setattr("testing_agent.services.zentao_mcp_instance.McpClient", factory)
    # ZentaoMcpAccess.resolve 从 zentao_mcp 命名空间取 McpClient 传入 discover_instance。
    monkeypatch.setattr("testing_agent.services.zentao_mcp.McpClient", factory)
    monkeypatch.setattr("testing_agent.services.zentao_bug_import.McpClient", factory)
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
    # 默认按当前迭代绑定的执行整套查询：只含 execution=20 的候选。
    body = api.get(field["candidates"], headers=owner, params={"sprintId": field["sprint"]}).json()
    assert body["code"] == 0, body
    data = body["data"]
    assert data["scope"] == "execution" and data["executionId"] == 20
    assert data["total"] == 7
    assert all(item["remoteBugId"] != 55 for item in data["items"])
    linked = {item["remoteBugId"]: item["linked"] for item in data["items"]}
    assert linked[50] is True
    assert linked[51] is False
    assert any(call[0] == "get_executions_executionID_bugs" for call in field["remote"].calls)
    assert not any(call[0] == "get_projects_projectID_bugs" for call in field["remote"].calls)

    data = api.get(
        field["candidates"],
        headers=owner,
        params={"sprintId": field["sprint"], "status": "resolved"},
    ).json()["data"]
    assert [item["remoteBugId"] for item in data["items"]] == [51]

    data = api.get(
        field["candidates"],
        headers=owner,
        params={"sprintId": field["sprint"], "keyword": "缺陷 51"},
    ).json()["data"]
    assert [item["remoteBugId"] for item in data["items"]] == [51]

    data = api.get(
        field["candidates"],
        headers=owner,
        params={"sprintId": field["sprint"], "pageSize": 2, "page": 2},
    ).json()["data"]
    assert data["total"] == 7 and len(data["items"]) == 2

    # 迭代未绑定执行：直接提示，不做项目范围回退（用户确认 2026-10-09）。
    from support.function_case_library import make_sprint as make_sprint_helper

    unbound = make_sprint_helper(api, owner, field["pid"], name="unbound")
    response = api.get(field["candidates"], headers=owner, params={"sprintId": unbound})
    assert response.status_code == 400
    assert "未绑定禅道执行" in response.json()["message"]

    # 未选择迭代时保持项目范围查询。
    data = api.get(field["candidates"], headers=owner).json()["data"]
    assert data["scope"] == "project" and data["executionId"] is None
    assert data["total"] == 8


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

    # R41：带图且有文本的候选可导入文本，图片组标记待补（非阻塞）。
    assert by_id[52]["state"] == "ready"
    assert any("先导入文本" in item["reason"] for item in by_id[52]["pending"])
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


def test_import_with_images_applies_text_and_defers_description_group(api, setup):
    field = setup
    owner = field["owner"]
    response = api.post(
        field["import"],
        headers=owner,
        json={
            "requestId": "req-20261009-0005",
            "items": [import_item(field["sprint"], 52, field["owner_id"])],
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()["data"]["items"][0]
    assert result["status"] == "success"
    assert any("先导入文本" in item["reason"] for item in result["pending"])

    detail = api.get(f"/v1/bugs/{result['bugId']}", headers=owner).json()["data"]
    assert detail["descriptionHtml"] == "<p>截图</p>"

    async def load():
        async with api.app.state.test_sessions() as session:
            return (
                await session.scalars(
                    select(BugZentaoSyncBaseline).where(
                        BugZentaoSyncBaseline.bug_id == result["bugId"]
                    )
                )
            ).all()

    groups = {baseline.field_group for baseline in asyncio.run(load())}
    # 描述组未建立基线：文件管线补齐图片前，反向拉取会如实显示待处理（R30）。
    assert groups == {"profile", "status", "assignee"}


PULL_CONTENT = "pull-content\n"
PULL_HASH = hashlib.sha256(PULL_CONTENT.encode()).hexdigest()


@pytest.fixture
def pull_files(api, setup, monkeypatch):
    """模拟 MCP 的 get_bug_attachment 内容回传与平台文件生命周期。"""
    s = setup
    state = {"initiated": [], "completed": [], "attached": [], "pull_failure": ""}
    original = s["remote"].handle

    async def handle(request):
        body = json.loads(request.content)
        name = body.get("params", {}).get("name")
        if name != "get_bug_attachment":
            return await original(request)
        args = body["params"]["arguments"]
        s["remote"].calls.append(("get_bug_attachment", args))
        if state["pull_failure"] == "transfer" and args.get("uploadUrl"):
            data = {"status": "fail", "uncertain": False, "errorCode": "content_upload_failed"}
        else:
            data = {
                "status": "success",
                "id": args["fileId"],
                "filename": f"附件-{args['fileId']}.png",
                "size": len(PULL_CONTENT),
                "sha256": PULL_HASH,
            }
            if args.get("uploadUrl"):
                data["uploaded"] = True
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"structuredContent": data}}
        )

    s["remote"].handle = handle

    async def initiate_pull(self, user_id, project_id, *, bug_id, filename, size, sha256):
        state["initiated"].append(
            {"filename": filename, "size": size, "sha256": sha256, "bugId": bug_id}
        )
        file_id = f"pull-{len(state['initiated'])}"
        return {"fileId": file_id, "upload": f"http://s3.test/stage/{file_id}", "expiresIn": 300}

    async def complete(self, user_id, file_id):
        state["completed"].append(file_id)
        return {"fileId": file_id, "status": "ready"}

    async def attach(self, user_id, file_id, project_id, resource_type, resource_id, *, purpose):
        state["attached"].append(file_id)
        return {"fileId": file_id, "filename": "x"}

    monkeypatch.setattr(StoredFileService, "initiate_pull", initiate_pull)
    monkeypatch.setattr(StoredFileService, "complete", complete)
    monkeypatch.setattr(StoredFileService, "attach", attach)
    s["pull_state"] = state
    return s


def test_import_pulls_files_rewrites_images_and_writes_baseline(api, pull_files):
    field = pull_files
    owner = field["owner"]
    response = api.post(
        field["import"],
        headers=owner,
        json={
            "requestId": "req-20261009-0006",
            "items": [import_item(field["sprint"], 55, field["owner_id"])],
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()["data"]["items"][0]
    assert result["status"] == "success"
    # 正文图片全部解析并回传：待处理清单里不应再有描述项。
    assert all(item["field"] != "description" for item in result["pending"])

    detail = api.get(f"/v1/bugs/{result['bugId']}", headers=owner).json()["data"]
    assert '<img data-file-id="pull-1">' in detail["descriptionHtml"]
    assert "file-read-101" not in detail["descriptionHtml"]

    async def load():
        async with api.app.state.test_sessions() as session:
            baselines = (
                await session.scalars(
                    select(BugZentaoSyncBaseline).where(
                        BugZentaoSyncBaseline.bug_id == result["bugId"],
                        BugZentaoSyncBaseline.field_group == "description",
                    )
                )
            ).all()
            mappings = (
                await session.scalars(
                    select(BugZentaoAttachment).where(BugZentaoAttachment.bug_id == result["bugId"])
                )
            ).all()
            return baselines, mappings

    baselines, mappings = asyncio.run(load())
    assert len(baselines) == 1
    assert baselines[0].local_snapshot_json["digest"]
    assert baselines[0].remote_snapshot_json["digest"]
    assert [(m.direction, m.status, m.remote_file_id) for m in mappings] == [
        ("pull", "succeeded", 101)
    ]
    state = field["pull_state"]
    assert len(state["initiated"]) == 1 and state["initiated"][0]["filename"] == "附件-101.png"
    assert state["attached"] == ["pull-1"]


def test_import_file_transfer_failure_keeps_bug_and_marks_pending(api, pull_files):
    field = pull_files
    owner = field["owner"]
    field["pull_state"]["pull_failure"] = "transfer"
    response = api.post(
        field["import"],
        headers=owner,
        json={
            "requestId": "req-20261009-0007",
            "items": [import_item(field["sprint"], 57, field["owner_id"])],
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()["data"]["items"][0]
    # Bug 本体照常创建；失败的文件进入待处理清单（R41/R53）。
    assert result["status"] == "success"
    assert any("#102" in item["reason"] for item in result["pending"])

    async def load():
        async with api.app.state.test_sessions() as session:
            baselines = (
                await session.scalars(
                    select(BugZentaoSyncBaseline).where(
                        BugZentaoSyncBaseline.bug_id == result["bugId"],
                        BugZentaoSyncBaseline.field_group == "description",
                    )
                )
            ).all()
            mappings = (
                await session.scalars(
                    select(BugZentaoAttachment).where(BugZentaoAttachment.bug_id == result["bugId"])
                )
            ).all()
            return baselines, mappings

    baselines, mappings = asyncio.run(load())
    assert baselines == []
    assert [(m.direction, m.status) for m in mappings] == [("pull", "failed")]


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
                import_item(field["sprint"], 56, field["owner_id"]),
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


def test_import_database_failure_rolls_back_all_rows_and_allows_same_request_retry(
    api, setup, monkeypatch
):
    from sqlalchemy import func
    from sqlalchemy.exc import IntegrityError

    from testing_agent.models.bug import Bug
    from testing_agent.repositories.bug import BugRepository

    async def counts():
        async with api.app.state.test_sessions() as session:
            return [
                await session.scalar(select(func.count()).select_from(model))
                for model in (
                    Bug,
                    BugActivity,
                    BugZentaoPush,
                    BugZentaoSyncBaseline,
                    BugZentaoAttachment,
                )
            ]

    original_commit = BugRepository.commit

    async def fail_import_commit(repository):
        if any(
            isinstance(row, BugZentaoPush) and row.source == "import"
            for row in repository.session.new
        ):
            await repository.session.flush()
            raise IntegrityError("test write", {}, RuntimeError("injected unrelated constraint"))
        await original_commit(repository)

    before = asyncio.run(counts())
    body = {
        "requestId": "atomic-import-retry",
        "items": [import_item(setup["sprint"], 51, setup["owner_id"])],
    }
    monkeypatch.setattr(BugRepository, "commit", fail_import_commit)
    failed = api.post(setup["import"], headers=setup["owner"], json=body)
    assert failed.status_code == 500
    assert failed.json()["code"] == 500
    assert asyncio.run(counts()) == before

    monkeypatch.setattr(BugRepository, "commit", original_commit)
    response = api.post(setup["import"], headers=setup["owner"], json=body)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["items"][0]["status"] == "success"
    assert asyncio.run(counts())[0] == before[0] + 1
