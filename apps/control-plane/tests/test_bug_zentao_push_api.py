"""Real auth/database/HTTP API and MCP protocol, with only the remote transport replaced."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from integration_test_driver import dispatch_sync, enable
from sqlalchemy import select
from test_bug_api import create_bug
from test_function_case_library import make_requirement, make_sprint
from test_project_membership_api import account, project
from test_project_membership_api import api as api

from testing_agent.models.bug_zentao_push import BugZentaoPush
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


def test_local_submission_context_does_not_contact_mcp(api, setup, monkeypatch):
    from testing_agent.api.deps import build_bug_service, get_integration_connection_service
    from testing_agent.core.config import get_settings
    from testing_agent.models.bug import Bug
    from testing_agent.services.bug_zentao_push import BugZentaoPushService

    async def forbidden_discovery(*args, **kwargs):
        raise AssertionError("Local submission must not contact MCP")

    monkeypatch.setattr(
        "testing_agent.services.bug_zentao_push.discover_instance", forbidden_discovery
    )

    async def inspect_context():
        async with api.app.state.test_sessions() as session:
            settings = get_settings()
            pushes = BugZentaoPushService(
                build_bug_service(session, settings),
                get_integration_connection_service(session, settings),
            )
            bug = await session.scalar(select(Bug).where(Bug.bug_id == setup["bug"]["bugId"]))
            service, own, target = await pushes.local_context(bug, bug.reporter_user_id)
            assert service.service_id == setup["sid"]
            assert own.user_id == bug.reporter_user_id
            assert target["instanceUrl"] == INSTANCE
            assert [target[key] for key in ("project", "execution", "story")] == [10, 20, 30]

    asyncio.run(inspect_context())


def test_manual_push_uses_bindings_persists_result_and_never_recreates(api, setup):
    s = setup
    assert s["remote"].writes == []  # Local creation does not invoke MCP.
    status = api.get(s["url"], headers=s["owner"])
    assert status.json()["data"]["ready"] is True
    assert s["remote"].calls == []  # Status/preview is local, no remote writes or reads.
    result = dispatch_sync(api, s, headers=s["owner"])
    assert result.status_code == 200, result.text
    data = result.json()["data"]
    assert data["status"] == "succeeded" and data["remoteBugId"] == 50
    assert s["remote"].writes[0]["payload"] == {
        "title": "登录失败",
        "steps": "<p>现象与复现步骤</p>",
        "severity": 2,
        "pri": 1,
        "project": 10,
        "execution": 20,
        "story": 30,
        "productID": 40,
        "openedBuild": ["trunk"],
    }
    assert set(s["remote"].headers) == {"owner-secret"}
    assert set(s["remote"].endpoints) == {"http://mcp.test/zentao/mcp"}
    assert "owner-secret" not in result.text
    assert dispatch_sync(api, s, headers=s["owner"]).json()["data"]["remoteBugId"] == 50
    assert api.get(s["url"], headers=s["owner"]).json()["data"]["status"] == "succeeded"
    assert len(s["remote"].writes) == 1
    records = api.get(f"/v1/bugs/{s['bug']['bugId']}/activities", headers=s["owner"])
    assert any(item["action"] == "zentao_sync_job" for item in records.json()["data"]["items"])


@pytest.mark.parametrize("mutation", ["missing-requirement", "wrong-parent", "wrong-instance"])
def test_invalid_local_binding_prevents_remote_calls(api, setup, mutation):
    from testing_agent.models.bug import Bug
    from testing_agent.models.shared_service import SharedService

    s = setup
    if mutation == "missing-requirement":
        change(api, Bug, "requirement_id", "", bug_id=s["bug"]["bugId"])
    elif mutation == "wrong-parent":
        change(api, ResourceBinding, "remote_parent_id", "999", binding_id="requirement-binding")
    else:
        change(api, SharedService, "zentao_instance_url", "http://other.test", service_id=s["sid"])
    assert api.get(s["url"], headers=s["owner"]).json()["data"]["ready"] is False
    assert dispatch_sync(api, s, headers=s["owner"]).status_code == (
        409 if mutation == "wrong-instance" else 400
    )
    assert s["remote"].calls == []


def test_remote_hierarchy_change_is_rejected_before_creation(api, setup):
    setup["remote"].project_id = 999
    result = dispatch_sync(api, setup, headers=setup["owner"])
    assert result.json()["data"]["latestJob"]["jobStatus"] == "failed"
    assert setup["remote"].writes == []


def test_members_must_use_their_own_authorization_and_viewers_cannot_push(api, setup):
    s = setup
    s["remote"].headers.clear()
    _, member = account(api, "member")
    _, viewer = account(api, "viewer")
    _, developer = account(api, "developer")
    for name, role in [("member", "member"), ("viewer", "viewer"), ("developer", "developer")]:
        assert (
            api.post(
                f"/v1/projects/{s['pid']}/members",
                headers=s["owner"],
                json={"name": name, "role": role},
            ).status_code
            == 200
        )
    assert dispatch_sync(api, s, headers=member).status_code == 400
    assert dispatch_sync(api, s, headers=viewer).status_code == 403
    assert dispatch_sync(api, s, headers=developer).status_code == 403
    assert api.get(s["url"], headers=developer).status_code == 200
    assert s["remote"].calls == []
    assert (
        api.put(
            f"{s['path']}/{s['sid']}/authorization", headers=member, json={"token": "member-secret"}
        ).status_code
        == 200
    )
    assert dispatch_sync(api, s, headers=member).json()["data"]["status"] == "succeeded"
    assert set(s["remote"].headers) == {"member-secret"}


def test_upstream_403_is_a_known_failure_and_safe_retry_succeeds(api, setup):
    s = setup
    s["remote"].failure = "403"
    first = dispatch_sync(api, s, headers=s["owner"]).json()["data"]
    assert first["status"] == "failed" and "明确拒绝" in first["errorMessage"]
    assert first["remoteBugId"] is None
    s["remote"].failure = ""
    assert dispatch_sync(api, s, headers=s["owner"]).json()["data"]["status"] == "succeeded"


@pytest.mark.parametrize("failure", ["timeout", "missing-id", "missing-status"])
def test_ambiguous_create_blocks_retries_and_can_reconcile_without_new_write(api, setup, failure):
    s = setup
    s["remote"].failure = failure
    first = dispatch_sync(api, s, headers=s["owner"])
    assert first.json()["data"]["status"] == "unknown"
    assert "secret-must-not-leak" not in first.text
    assert dispatch_sync(api, s, headers=s["owner"]).status_code == 409
    assert len(s["remote"].writes) == 1
    bad = api.post(f"{s['url']}/reconcile", headers=s["owner"], json={"remoteBugId": 999})
    assert bad.status_code == 400
    good = api.post(f"{s['url']}/reconcile", headers=s["owner"], json={"remoteBugId": 50})
    assert good.status_code == 200, good.text
    assert good.json()["data"]["status"] == "succeeded"
    assert len(s["remote"].writes) == 1


def test_concurrent_pushes_reserve_before_the_remote_write(api, setup):
    s = setup
    s["remote"].block = True
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(dispatch_sync, api, s, headers=s["owner"])
        assert s["remote"].entered.wait(timeout=10)
        try:
            second = workers.submit(dispatch_sync, api, s, headers=s["owner"])
            assert second.result(timeout=10).status_code == 409
        finally:
            s["remote"].release.set()
        assert first.result(timeout=10).json()["data"]["status"] == "succeeded"
    assert len(s["remote"].writes) == 1


def test_crashed_creation_is_not_retried(api, setup):
    s = setup
    s["remote"].failure = "timeout"
    dispatch_sync(api, s, headers=s["owner"])
    change(api, BugZentaoPush, "status", "creating", bug_id=s["bug"]["bugId"])
    change(
        api,
        BugZentaoPush,
        "updated_at",
        datetime.now(UTC) - timedelta(minutes=10),
        bug_id=s["bug"]["bugId"],
    )
    assert api.get(s["url"], headers=s["owner"]).json()["data"]["status"] == "unknown"
    assert dispatch_sync(api, s, headers=s["owner"]).status_code == 409
    assert len(s["remote"].writes) == 1


def test_instance_identity_is_read_from_mcp_and_cannot_be_spoofed(api, setup):
    s = setup
    response = api.patch(
        f"{s['path']}/{s['sid']}",
        headers=s["owner"],
        json={"name": "禅道 MCP", "zentaoInstanceUrl": "http://other.test"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["zentaoInstanceUrl"] == INSTANCE
    assert api.get(s["url"], headers=s["owner"]).json()["data"]["ready"] is True


def test_revoked_authorization_during_validation_prevents_creation(api, setup):
    from sqlalchemy import update

    from testing_agent.models.integration_connection import IntegrationConnection

    async def revoke():
        async with api.app.state.test_sessions() as session:
            await session.execute(
                update(IntegrationConnection)
                .where(IntegrationConnection.provider == "mcp")
                .values(status="invalid")
            )
            from testing_agent.services.worker_authorization import revoke_executions

            await revoke_executions(session, actor=setup["bug"]["reporterUserId"])
            await session.commit()

    setup["remote"].on_verify = revoke
    result = dispatch_sync(api, setup, headers=setup["owner"])
    assert result.json()["data"]["latestJob"]["jobStatus"] == "canceled"
    assert setup["remote"].writes == []


def test_abandoned_preparation_can_retry_but_images_are_not_transferred(api, setup):
    from testing_agent.models.bug import Bug

    s = setup
    s["remote"].project_id = 999
    assert (
        dispatch_sync(api, s, headers=s["owner"]).json()["data"]["latestJob"]["jobStatus"]
        == "failed"
    )

    async def legacy_preparation():
        async with api.app.state.test_sessions() as session:
            session.add(
                BugZentaoPush(
                    bug_id=s["bug"]["bugId"],
                    operation_id="legacy-preparing",
                    actor_user_id=s["bug"]["reporterUserId"],
                    service_id=s["sid"],
                    instance_url=INSTANCE,
                    status="preparing",
                    target_json={"project": 10, "execution": 20, "story": 30},
                    payload_json={},
                    updated_at=datetime.now(UTC) - timedelta(minutes=10),
                )
            )
            await session.commit()

    asyncio.run(legacy_preparation())
    change(api, Bug, "description_html", "<p>正文</p>", bug_id=s["bug"]["bugId"])
    s["remote"].project_id = 10
    assert api.get(s["url"], headers=s["owner"]).json()["data"]["ready"] is True
    assert dispatch_sync(api, s, headers=s["owner"]).json()["data"]["status"] == "succeeded"
    assert s["remote"].writes[0]["payload"]["steps"] == "<p>正文</p>"


def test_push_history_requires_owner_confirmation_after_bindings_and_service_are_removed(
    api, setup
):
    from sqlalchemy import delete

    s = setup
    result = dispatch_sync(api, s, headers=s["owner"])
    assert result.json()["data"]["status"] == "succeeded"

    async def remove_bindings():
        async with api.app.state.test_sessions() as session:
            await session.execute(delete(ResourceBinding))
            await session.commit()

    asyncio.run(remove_bindings())
    assert api.delete(f"{s['path']}/{s['sid']}", headers=s["owner"]).status_code == 200
    s["remote"].instance = "http://other-zen.test"
    created = api.post(
        s["path"],
        headers=s["owner"],
        json={"name": "ZenTao-MCP", "templateId": "zentao", "baseUrl": "http://new-mcp.test/mcp"},
    ).json()["data"]
    authorization = f"{s['path']}/{created['serviceId']}/authorization"
    pending = api.put(authorization, headers=s["owner"], json={"token": "new-secret"})
    assert pending.status_code == 200, pending.text
    assert pending.json()["data"]["instanceResetRequired"] is True
    assert api.get(s["url"], headers=s["owner"]).json()["data"]["remoteBugId"] == 50
    assert len(s["remote"].writes) == 1


def test_confirmed_switch_archives_bug_and_attachment_associations(api, setup):
    from testing_agent.models.bug import Bug
    from testing_agent.models.bug_activity import BugActivity
    from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment

    s = setup
    result = dispatch_sync(api, s, headers=s["owner"])
    assert result.json()["data"]["status"] == "succeeded"
    bug_id = s["bug"]["bugId"]

    async def seed_attachment():
        async with api.app.state.test_sessions() as session:
            session.add(
                BugZentaoAttachment(
                    bug_id=bug_id,
                    file_id="retained-local-file",
                    sha256="checksum",
                    instance_url=INSTANCE,
                    remote_bug_id=50,
                    remote_file_id=90,
                    operation_id="old-attachment",
                    actor_user_id="old-actor",
                    status="succeeded",
                )
            )
            await session.commit()

    asyncio.run(seed_attachment())
    s["remote"].instance = "http://new-zen.test"
    endpoint = f"{s['path']}/{s['sid']}/instance-reset"
    switched = api.post(endpoint, headers=s["owner"], json={"instanceUrl": "http://new-zen.test"})
    assert switched.status_code == 200, switched.text

    async def check():
        async with api.app.state.test_sessions() as session:
            assert await session.scalar(select(Bug).where(Bug.bug_id == bug_id)) is not None
            assert await session.scalar(select(ResourceBinding)) is None
            assert await session.scalar(select(BugZentaoPush)) is None
            assert await session.scalar(select(BugZentaoAttachment)) is None
            activity = await session.scalar(
                select(BugActivity).where(BugActivity.action == "zentao_instance_reset")
            )
            old = activity.detail_json["previousAssociation"]
            assert old["instanceUrl"] == INSTANCE
            assert old["remoteBugId"] == 50
            assert old["payload"]["title"] == s["bug"]["title"]
            assert old["attachments"][0]["remoteFileId"] == 90

    asyncio.run(check())
    assert len(s["remote"].writes) == 1
    assert api.get(s["url"], headers=s["owner"]).json()["data"]["remoteBugId"] is None


def test_switch_waits_for_an_active_bug_write_without_deleting_any_association(api, setup):
    s = setup
    assert dispatch_sync(api, s, headers=s["owner"]).json()["data"]["status"] == "succeeded"
    change(api, BugZentaoPush, "status", "creating", bug_id=s["bug"]["bugId"])
    s["remote"].instance = "http://new-zen.test"
    original = api.get(s["path"], headers=s["owner"]).json()["data"]["items"][0]["baseUrl"]
    switched = api.patch(
        f"{s['path']}/{s['sid']}",
        headers=s["owner"],
        json={
            "name": "ZenTao-MCP",
            "baseUrl": "http://next-mcp.test/zentao/mcp",
            "confirmInstanceSwitch": True,
        },
    )
    assert switched.status_code == 409
    assert "正在推送" in switched.json()["message"]
    assert api.get(s["path"], headers=s["owner"]).json()["data"]["items"][0]["baseUrl"] == original

    async def check():
        async with api.app.state.test_sessions() as session:
            assert len(list(await session.scalars(select(ResourceBinding)))) == 3
            assert await session.scalar(select(BugZentaoPush)) is not None

    asyncio.run(check())


def test_switch_waits_for_attachment_uploads(api, setup):
    from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment

    s = setup
    assert dispatch_sync(api, s, headers=s["owner"]).json()["data"]["status"] == "succeeded"

    async def seed():
        async with api.app.state.test_sessions() as session:
            session.add(
                BugZentaoAttachment(
                    bug_id=s["bug"]["bugId"],
                    file_id="pending-file",
                    sha256="checksum",
                    instance_url=INSTANCE,
                    remote_bug_id=50,
                    operation_id="pending",
                    actor_user_id="actor",
                    status="uploading",
                )
            )
            await session.commit()

    asyncio.run(seed())
    s["remote"].instance = "http://new-zen.test"
    reset = api.post(
        f"{s['path']}/{s['sid']}/instance-reset",
        headers=s["owner"],
        json={"instanceUrl": "http://new-zen.test"},
    )
    assert reset.status_code == 409
    assert "附件正在同步" in reset.json()["message"]


@pytest.mark.parametrize("authorized", [True, False])
def test_push_inherits_project_mcp_and_cannot_borrow_other_service_authorization(
    api, setup, authorized
):
    s = setup
    created = api.post(
        s["path"],
        headers=s["owner"],
        json={
            "name": "项目所选 MCP",
            "templateId": "zentao",
            "baseUrl": "http://selected.test/mcp",
        },
    )
    assert created.status_code == 200, created.text
    sid = created.json()["data"]["serviceId"]
    if authorized:
        assert (
            api.put(
                f"{s['path']}/{sid}/authorization",
                headers=s["owner"],
                json={"token": "selected-secret"},
            ).status_code
            == 200
        )
    change(api, ResourceBinding, "extra_json", {"mcpServiceId": sid}, binding_id="project-binding")
    # Stale child metadata must not override the root project's decision.
    change(
        api,
        ResourceBinding,
        "extra_json",
        {"mcpServiceId": s["sid"]},
        binding_id="requirement-binding",
    )
    s["remote"].headers.clear()
    s["remote"].endpoints.clear()
    response = dispatch_sync(api, s, headers=s["owner"])
    if authorized:
        assert response.status_code == 200, response.text
        assert response.json()["data"]["mcpServiceId"] == sid
        assert set(s["remote"].endpoints) == {"http://selected.test/mcp"}
        assert set(s["remote"].headers) == {"selected-secret"}
        assert len(s["remote"].writes) == 1
    else:
        assert response.status_code == 400, response.text
        assert not s["remote"].writes
        assert not s["remote"].headers


@pytest.mark.parametrize("pending", [False, True])
def test_same_instance_project_switch_updates_push_transport_or_rejects_unresolved_write(
    api, setup, monkeypatch, pending
):
    s = setup
    monkeypatch.setattr(
        "testing_agent.services.zentao_mcp.McpClient",
        lambda url, token: McpClient(url, token, transport=httpx.MockTransport(s["remote"].handle)),
    )
    response = dispatch_sync(api, s, headers=s["owner"])
    assert response.status_code == 200, response.text
    if pending:
        change(api, BugZentaoPush, "status", "unknown", bug_id=s["bug"]["bugId"])
    created = api.post(
        s["path"],
        headers=s["owner"],
        json={"name": "新传输", "templateId": "zentao", "baseUrl": "http://new-transport.test/mcp"},
    )
    sid = created.json()["data"]["serviceId"]
    assert (
        api.put(
            f"{s['path']}/{sid}/authorization", headers=s["owner"], json={"token": "new-secret"}
        ).status_code
        == 200
    )
    response = api.patch(
        f"/v1/projects/{s['pid']}/bindings/project-binding",
        headers=s["owner"],
        json={"remoteResourceId": "10", "mcpServiceId": sid},
    )
    assert response.status_code == (409 if pending else 200), response.text

    async def inspect_push():
        async with api.app.state.test_sessions() as session:
            row = await session.scalar(
                select(BugZentaoPush).where(BugZentaoPush.bug_id == s["bug"]["bugId"])
            )
            assert row.remote_bug_id == 50
            assert row.service_id == (s["sid"] if pending else sid)

    asyncio.run(inspect_push())
    assert len(s["remote"].writes) == 1
