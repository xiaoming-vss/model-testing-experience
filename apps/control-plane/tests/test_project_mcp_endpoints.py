"""Project addresses and historical targets are enforced at the real HTTP boundary."""

import asyncio
import json

import httpx
import pytest
from sqlalchemy import select
from support.project_api import account, project
from support.project_api import api as api

from testing_agent.models.shared_service import SharedService
from testing_agent.services.mcp_client import McpClient


@pytest.fixture
def remote(monkeypatch):
    state = {"calls": [], "targets": {}, "offline": False}

    def handle(request):
        if state["offline"]:
            raise httpx.ConnectError("private upstream details", request=request)
        endpoint = str(request.url)
        token = request.headers["token"]
        body = json.loads(request.content)
        state["calls"].append((endpoint, token, body))
        if body["method"] == "notifications/initialized":
            return httpx.Response(202)
        if body["method"] == "initialize":
            result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}}
        elif body["params"]["name"] == "get_zentao_instance":
            target = state["targets"].get(endpoint, "https://zentao-a.test/subpath")
            result = {
                "structuredContent": {
                    "schemaVersion": 1,
                    "instanceUrl": target,
                    "apiBaseUrl": target + "/api.php/v2",
                }
            }
        elif body["params"]["name"] == "get_projects":
            result = {
                "structuredContent": {"projects": [{"id": "10", "name": "Project"}], "total": 1}
            }
        else:
            raise AssertionError("Unexpected business request")
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    def factory(endpoint, token):
        return McpClient(endpoint, token, transport=httpx.MockTransport(handle))

    monkeypatch.setattr("testing_agent.services.zentao_mcp_instance.McpClient", factory)
    monkeypatch.setattr("testing_agent.services.zentao_mcp.McpClient", factory)
    return state


def configure(api, owner, name, endpoint):
    pid = project(api, owner, name)
    path = f"/v1/projects/{pid}/services/mcp"
    response = api.post(
        path, headers=owner, json={"name": "custom", "baseUrl": endpoint, "templateId": "zentao"}
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["baseUrl"] == endpoint
    assert data["name"] == "custom"
    assert data["connectionStatus"] == "unchecked"
    return pid, path + "/" + data["serviceId"]


def authorize(api, headers, service, token):
    response = api.put(service + "/authorization", headers=headers, json={"token": token})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_two_projects_call_their_own_endpoints_with_the_current_members_token(api, remote):
    _, owner = account(api, "owner")
    _, member = account(api, "member")
    endpoints = ["http://mcp-a.test:9091/zentao/mcp/", "https://mcp-b.test/custom/zentao/mcp"]
    for index, endpoint in enumerate(endpoints):
        remote["targets"][endpoint] = f"https://zentao-{index}.test/subpath"
        pid, service = configure(api, owner, f"project-{index}", endpoint)
        api.post(
            f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
        )
        authorize(api, owner, service, f"owner-{index}")
        authorize(api, member, service, f"member-{index}")
        remote["calls"].clear()
        response = api.get(f"/v1/projects/{pid}/zentao/mcp/projects", headers=member)
        assert response.status_code == 200, response.text
        assert remote["calls"]
        assert {(url, token) for url, token, _ in remote["calls"]} == {
            (endpoint, f"member-{index}")
        }
        api.delete(service + "/authorization", headers=member)
        assert api.get(f"/v1/projects/{pid}/zentao/mcp/projects", headers=member).status_code == 400
        assert api.get(f"/v1/projects/{pid}/zentao/mcp/projects", headers=owner).status_code == 200


def test_same_target_endpoint_change_keeps_personal_authorizations(api, remote):
    _, owner = account(api, "owner")
    pid, service = configure(api, owner, "project-a", "http://mcp-a.test/zentao/mcp")
    before = authorize(api, owner, service, "owner-token")
    assert (
        api.post(
            f"/v1/projects/{pid}/bindings",
            headers=owner,
            json={"provider": "zentao", "remoteResourceId": "10"},
        ).status_code
        == 200
    )
    response = api.patch(
        service,
        headers=owner,
        json={
            "name": "ZenTao-MCP",
            "baseUrl": "https://new-mcp.test/routed/mcp/",
            "confirmInstanceSwitch": True,
        },
    )
    assert response.status_code == 200, response.text
    assert (
        response.json()["data"]["authorization"]["connectionId"]
        == before["authorization"]["connectionId"]
    )
    remote["calls"].clear()
    assert api.get(f"/v1/projects/{pid}/zentao/mcp/projects", headers=owner).status_code == 200
    assert {url for url, _, _ in remote["calls"]} == {"https://new-mcp.test/routed/mcp/"}
    assert response.json()["data"]["instanceResetRequired"] is False
    assert api.get(f"/v1/projects/{pid}/bindings", headers=owner).json()["data"]["total"] == 1
    assert (
        api.post(
            service + "/instance-reset",
            headers=owner,
            json={"instanceUrl": "https://zentao-a.test/subpath"},
        ).status_code
        == 409
    )


def test_changed_target_requires_owner_confirmation_and_invalidates_others(api, remote):
    _, owner = account(api, "owner")
    _, member = account(api, "member")
    endpoint = "http://mcp-a.test/zentao/mcp"
    pid, service = configure(api, owner, "project-a", endpoint)
    api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
    )
    authorize(api, owner, service, "owner-old")
    authorize(api, member, service, "member-old")
    remote["targets"][endpoint] = "https://zentao-b.test"
    remote["calls"].clear()
    assert api.get(f"/v1/projects/{pid}/zentao/mcp/projects", headers=owner).status_code == 409
    assert all(
        body.get("params", {}).get("name") != "get_projects" for _, _, body in remote["calls"]
    )
    pending = authorize(api, owner, service, "owner-new")
    assert pending["instanceResetRequired"] is True
    confirmed = api.patch(
        service,
        headers=owner,
        json={"name": "ZenTao-MCP", "baseUrl": endpoint, "confirmInstanceSwitch": True},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["data"]["authorization"]["status"] == "authorized"
    listing = api.get(f"/v1/projects/{pid}/services/mcp", headers=member).json()["data"]["items"][0]
    assert listing["authorization"]["status"] == "invalid"
    assert api.get(f"/v1/projects/{pid}/zentao/mcp/projects", headers=member).status_code == 400
    authorize(api, member, service, "member-new")
    assert api.get(f"/v1/projects/{pid}/zentao/mcp/projects", headers=member).status_code == 200


def test_recreated_catalog_preserves_bindings_until_owner_confirms_target_switch(api, remote):
    _, owner = account(api, "owner")
    endpoint = "http://mcp-a.test/zentao/mcp"
    pid, service = configure(api, owner, "project-a", endpoint)
    authorize(api, owner, service, "owner-token")
    response = api.post(
        f"/v1/projects/{pid}/bindings",
        headers=owner,
        json={"provider": "zentao", "remoteResourceId": "10"},
    )
    assert response.status_code == 200, response.text
    assert api.delete(service, headers=owner).status_code == 200
    remote["targets"][endpoint] = "https://zentao-b.test"
    response = api.post(
        f"/v1/projects/{pid}/services/mcp",
        headers=owner,
        json={"name": "ZenTao-MCP", "baseUrl": endpoint, "templateId": "zentao"},
    )
    sid = response.json()["data"]["serviceId"]
    new_service = f"/v1/projects/{pid}/services/mcp/{sid}"
    pending = authorize(api, owner, new_service, "new-token")
    assert pending["instanceResetRequired"] is True
    assert api.get(f"/v1/projects/{pid}/zentao/mcp/projects", headers=owner).status_code == 400
    assert api.get(f"/v1/projects/{pid}/bindings", headers=owner).json()["data"]["total"] == 1
    assert (
        api.post(
            new_service + "/instance-reset",
            headers=owner,
            json={"instanceUrl": "https://zentao-b.test"},
        ).status_code
        == 200
    )
    assert api.get(f"/v1/projects/{pid}/bindings", headers=owner).json()["data"]["total"] == 0
    assert api.get(f"/v1/projects/{pid}/zentao/mcp/projects", headers=owner).status_code == 200


def test_unreachable_endpoint_keeps_config_and_personal_token_without_leaking_error(api, remote):
    _, owner = account(api, "owner")
    pid, service = configure(api, owner, "project-a", "http://mcp-a.test/zentao/mcp")
    remote["offline"] = True
    response = authorize(api, owner, service, "personal-secret")
    assert response["authorization"]["status"] == "authorized"
    assert response["connectionStatus"] == "error"
    assert "personal-secret" not in str(response)
    assert "private upstream details" not in str(response)
    remote["offline"] = False
    assert api.get(f"/v1/projects/{pid}/zentao/mcp/projects", headers=owner).status_code == 200


def test_first_successful_authorization_persists_the_actual_instance(api, remote):
    _, owner = account(api, "owner")
    pid, service = configure(api, owner, "project-a", "http://mcp-a.test/zentao/mcp")
    authorize(api, owner, service, "owner-token")

    async def identity():
        async with api.app.state.test_sessions() as session:
            row = await session.scalar(select(SharedService).where(SharedService.project_id == pid))
            assert row.zentao_instance_url == "https://zentao-a.test/subpath"

    asyncio.run(identity())


def test_owner_confirmed_target_switch_clears_only_this_projects_zentao_bindings(api, remote):
    from test_function_case_library import make_requirement, make_sprint

    from testing_agent.models.resource_binding import ResourceBinding
    from testing_agent.models.shared_service import SharedService
    from testing_agent.models.test_order import TestOrder
    from testing_agent.models.test_order_entry import TestOrderEntry
    from testing_agent.services.service_instance import instance_key

    owner_id, owner = account(api, "switch-owner")
    _, member = account(api, "switch-member")
    pid, service = configure(api, owner, "switch-project", "http://switch-mcp.test/zentao/mcp")
    other_pid, _ = configure(api, owner, "untouched-project", "http://other-mcp.test/zentao/mcp")
    api.post(
        f"/v1/projects/{pid}/members",
        headers=owner,
        json={"name": "switch-member", "role": "member"},
    )
    authorize(api, owner, service, "owner-old")
    authorize(api, member, service, "member-old")
    sprint = make_sprint(api, owner, pid)
    requirement = make_requirement(api, owner, sprint)
    other_sprint = make_sprint(api, owner, other_pid)

    async def seed():
        async with api.app.state.test_sessions() as session:
            for identifier, provider, local_id, target in (
                ("switch-old", "zentao", pid, "https://zentao-a.test/subpath"),
                ("switch-sprint", "zentao", sprint, "https://zentao-a.test/subpath"),
                ("switch-req", "zentao", requirement, "https://zentao-a.test/subpath"),
                ("switch-gitlab", "gitlab", pid, "https://gitlab.test"),
                ("switch-other", "zentao", other_pid, "https://zentao-a.test/subpath"),
            ):
                session.add(
                    ResourceBinding(
                        binding_id=identifier,
                        user_id=owner_id["userId"],
                        provider=provider,
                        instance_url=target,
                        instance_key=instance_key(target),
                        connection_id="historical",
                        local_resource_type={
                            "switch-sprint": "sprint",
                            "switch-req": "requirement",
                        }.get(identifier, "project"),
                        local_resource_id=local_id,
                        remote_resource_type="project",
                        remote_resource_id="10",
                        status="active",
                    )
                )
            session.add_all(
                [
                    TestOrder(
                        order_id="switch-order", project_id=pid, sprint_id=sprint, name="switch"
                    ),
                    TestOrder(
                        order_id="other-order",
                        project_id=other_pid,
                        sprint_id=other_sprint,
                        name="untouched",
                    ),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    TestOrderEntry(
                        entry_id="switch-entry",
                        order_id="switch-order",
                        case_id="snapshot-case",
                        zentao_bug_id="old-42",
                        status="failed",
                        actual_results="preserved",
                    ),
                    TestOrderEntry(
                        entry_id="other-entry",
                        order_id="other-order",
                        case_id="other-case",
                        zentao_bug_id="keep-43",
                    ),
                ]
            )
            await session.commit()

    asyncio.run(seed())
    remote["targets"]["http://switch-mcp.test/zentao/mcp"] = "https://zentao-b.test"
    listing = api.get(f"/v1/projects/{pid}/services/mcp", headers=owner).json()["data"]["items"][0]
    assert listing["instanceResetRequired"] is True
    assert listing["pendingInstanceUrl"] == "https://zentao-b.test"
    assert (
        api.post(
            service + "/instance-reset",
            headers=member,
            json={"instanceUrl": "https://zentao-b.test"},
        ).status_code
        == 403
    )
    assert (
        api.post(
            service + "/instance-reset",
            headers=owner,
            json={"instanceUrl": "https://unexpected.test"},
        ).status_code
        == 409
    )
    switched = api.post(
        service + "/instance-reset", headers=owner, json={"instanceUrl": "https://zentao-b.test"}
    )
    assert switched.status_code == 200, switched.text
    assert switched.json()["data"]["authorization"]["status"] == "invalid"

    async def check():
        async with api.app.state.test_sessions() as session:
            identifiers = set(await session.scalars(select(ResourceBinding.binding_id)))
            assert identifiers == {"switch-gitlab", "switch-other"}
            entries = {row.entry_id: row for row in await session.scalars(select(TestOrderEntry))}
            assert entries["switch-entry"].zentao_bug_id == ""
            assert entries["switch-entry"].actual_results == "preserved"
            assert entries["switch-entry"].status == "failed"
            assert entries["other-entry"].zentao_bug_id == "keep-43"
            resource = await session.scalar(
                select(SharedService).where(SharedService.project_id == pid)
            )
            assert resource.zentao_instance_url == "https://zentao-b.test"

    asyncio.run(check())
    authorize(api, owner, service, "owner-new")
    assert api.get(f"/v1/projects/{pid}/zentao/mcp/projects", headers=owner).status_code == 200
    assert api.get(f"/v1/projects/{pid}/zentao/mcp/projects", headers=member).status_code == 400


def test_mixed_legacy_bindings_can_be_cleared_without_changing_the_current_token(api, remote):
    from testing_agent.models.resource_binding import ResourceBinding
    from testing_agent.services.service_instance import instance_key

    user, owner = account(api, "mixed-owner")
    pid, service = configure(api, owner, "mixed-project", "http://mixed.test/mcp")
    authorize(api, owner, service, "current-local-token")

    async def seed():
        async with api.app.state.test_sessions() as session:
            session.add(
                ResourceBinding(
                    binding_id="old-cloud",
                    user_id=user["userId"],
                    provider="zentao",
                    instance_url="https://old-cloud.test",
                    instance_key=instance_key("https://old-cloud.test"),
                    connection_id="historical",
                    local_resource_type="project",
                    local_resource_id=pid,
                    remote_resource_type="project",
                    remote_resource_id="10",
                    status="inactive",
                )
            )
            await session.commit()

    asyncio.run(seed())
    before = api.get(f"/v1/projects/{pid}/services/mcp", headers=owner).json()["data"]["items"][0]
    assert before["instanceResetRequired"] is True

    async def count():
        async with api.app.state.test_sessions() as session:
            return len(list(await session.scalars(select(ResourceBinding))))

    assert asyncio.run(count()) == 1  # GET and refresh never delete associations.
    remote["offline"] = True
    assert (
        api.post(
            service + "/instance-reset",
            headers=owner,
            json={"instanceUrl": before["pendingInstanceUrl"]},
        ).status_code
        == 502
    )
    assert asyncio.run(count()) == 1
    remote["offline"] = False
    cleared = api.post(
        service + "/instance-reset",
        headers=owner,
        json={"instanceUrl": before["pendingInstanceUrl"]},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["data"]["connectionStatus"] == "available"
    assert cleared.json()["data"]["authorization"]["status"] == "authorized"
    assert asyncio.run(count()) == 0


def test_edit_switch_confirmation_is_atomic_and_owner_only(api, remote):
    _, owner = account(api, "edit-owner")
    _, member = account(api, "edit-member")
    old = "http://old-mcp.test/mcp"
    new = "https://new-mcp.test/mcp"
    pid, service = configure(api, owner, "edit-project", old)
    api.post(
        f"/v1/projects/{pid}/members", headers=owner, json={"name": "edit-member", "role": "member"}
    )
    authorize(api, owner, service, "old-token")
    authorize(api, member, service, "member-token")
    assert (
        api.post(
            f"/v1/projects/{pid}/bindings",
            headers=owner,
            json={"provider": "zentao", "remoteResourceId": "10"},
        ).status_code
        == 200
    )
    remote["targets"][new] = "https://new-zentao.test"
    body = {"name": "ZenTao-MCP", "baseUrl": new}
    assert api.patch(service, headers=owner, json=body).status_code == 400
    body["confirmInstanceSwitch"] = True
    assert api.patch(service, headers=member, json=body).status_code == 403
    remote["offline"] = True
    assert api.patch(service, headers=owner, json=body).status_code == 502
    remote["offline"] = False
    listing = api.get(f"/v1/projects/{pid}/services/mcp", headers=owner).json()["data"]["items"][0]
    assert listing["baseUrl"] == old
    assert listing["authorization"]["status"] == "authorized"
    assert api.get(f"/v1/projects/{pid}/bindings", headers=owner).json()["data"]["total"] == 1
    saved = api.patch(service, headers=owner, json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["baseUrl"] == new
    assert saved.json()["data"]["instanceResetRequired"] is False
    assert saved.json()["data"]["authorization"]["status"] == "invalid"
    assert api.get(f"/v1/projects/{pid}/bindings", headers=owner).json()["data"]["total"] == 0

    async def check():
        async with api.app.state.test_sessions() as session:
            row = await session.scalar(select(SharedService).where(SharedService.project_id == pid))
            assert row.zentao_instance_url == "https://new-zentao.test"

    asyncio.run(check())
    authorize(api, owner, service, "new-token")
    assert api.get(f"/v1/projects/{pid}/zentao/mcp/projects", headers=owner).status_code == 200
    assert api.get(f"/v1/projects/{pid}/zentao/mcp/projects", headers=member).status_code == 400


def test_edit_switch_without_personal_token_preserves_endpoint(api, remote):
    _, owner = account(api, "no-token-owner")
    pid, service = configure(api, owner, "no-token-project", "http://original.test/mcp")
    failed = api.patch(
        service,
        headers=owner,
        json={
            "name": "ZenTao-MCP",
            "baseUrl": "http://changed.test/mcp",
            "confirmInstanceSwitch": True,
        },
    )
    assert failed.status_code == 400
    assert "Token" in failed.json()["message"]
    listing = api.get(f"/v1/projects/{pid}/services/mcp", headers=owner).json()["data"]["items"][0]
    assert listing["baseUrl"] == "http://original.test/mcp"


def test_concurrent_endpoint_change_during_check_does_not_clear_bindings(api, remote, monkeypatch):
    import testing_agent.services.shared_service as module

    _, owner = account(api, "concurrent-edit-owner")
    pid, service = configure(api, owner, "concurrent-edit", "http://original.test/mcp")
    authorize(api, owner, service, "personal-token")
    assert (
        api.post(
            f"/v1/projects/{pid}/bindings",
            headers=owner,
            json={"provider": "zentao", "remoteResourceId": "10"},
        ).status_code
        == 200
    )
    remote["targets"]["http://candidate.test/mcp"] = "https://new-zentao.test"
    original_discover = module.discover_instance

    async def concurrent_discover(endpoint, token):
        info = await original_discover(endpoint, token)
        async with api.app.state.test_sessions() as session:
            row = await session.scalar(select(SharedService).where(SharedService.project_id == pid))
            row.base_url = "http://concurrent.test/mcp"
            await session.commit()
        return info

    monkeypatch.setattr(module, "discover_instance", concurrent_discover)
    response = api.patch(
        service,
        headers=owner,
        json={
            "name": "ZenTao-MCP",
            "baseUrl": "http://candidate.test/mcp",
            "confirmInstanceSwitch": True,
        },
    )
    assert response.status_code == 409
    assert api.get(f"/v1/projects/{pid}/bindings", headers=owner).json()["data"]["total"] == 1

    async def check():
        async with api.app.state.test_sessions() as session:
            row = await session.scalar(select(SharedService).where(SharedService.project_id == pid))
            assert row.base_url == "http://concurrent.test/mcp"
            assert row.zentao_instance_url == "https://zentao-a.test/subpath"

    asyncio.run(check())


def test_named_mcp_creation_type_and_authorization_are_separate(api, remote):
    _, owner = account(api, "named-mcp-owner")
    pid = project(api, owner, "named-mcp-project")
    path = f"/v1/projects/{pid}/services/mcp"
    body = {"name": "  验收禅道  ", "baseUrl": "http://named-mcp.test/mcp", "templateId": "zentao"}
    unknown = api.post(path, headers=owner, json={**body, "templateId": "unknown"})
    assert unknown.status_code == 400
    created = api.post(path, headers=owner, json=body)
    assert created.status_code == 200, created.text
    data = created.json()["data"]
    assert data["name"] == "验收禅道"
    assert data["templateId"] == "zentao"
    assert data["authorization"]["status"] == "unauthorized"
    assert remote["calls"] == []
    duplicate = api.post(path, headers=owner, json={**body, "name": "第二个禅道"})
    assert duplicate.status_code == 200
    assert api.post(path, headers=owner, json=body).status_code == 409
    service = path + "/" + data["serviceId"]
    assert api.patch(service, headers=owner, json={"name": "重命名禅道"}).status_code == 200
    listed = next(
        row
        for row in api.get(path, headers=owner).json()["data"]["items"]
        if row["serviceId"] == data["serviceId"]
    )
    assert listed["name"] == "重命名禅道"
    assert listed["baseUrl"] == body["baseUrl"]
    authorized = authorize(api, owner, service, "own-test-token")
    assert authorized["name"] == "重命名禅道"
    assert authorized["authorization"]["status"] == "authorized"
    assert (
        api.get(
            f"/v1/projects/{pid}/zentao/mcp/projects",
            headers=owner,
            params={"mcpServiceId": data["serviceId"]},
        ).status_code
        == 200
    )
