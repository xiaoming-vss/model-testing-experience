"""Exercise real authentication, binding persistence and MCP transport together."""

import asyncio

import pytest
from sqlalchemy import select
from support.project_api import account
from support.project_api import api as api
from support.zentao_mcp_bindings_api import (
    Remote as Remote,
)
from support.zentao_mcp_bindings_api import (
    add_mcp as add_mcp,
)
from support.zentao_mcp_bindings_api import (
    bind as bind,
)
from support.zentao_mcp_bindings_api import (
    bind_parents as bind_parents,
)
from support.zentao_mcp_bindings_api import (
    setup as setup,
)

from testing_agent.models.resource_binding import ResourceBinding


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
