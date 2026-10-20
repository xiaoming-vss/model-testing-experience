"""Options and selected payloads through real auth, DB and HTTP/MCP boundaries."""

import asyncio

import pytest
from integration_test_driver import dispatch_sync, enable
from sqlalchemy import select
from support.bug_zentao_push_api import setup as setup
from support.project_api import account
from support.project_api import api as api

from testing_agent.models.bug_zentao_push import BugZentaoPush


@pytest.fixture(autouse=True)
def migration_mode(api):
    enable(api)


def test_options_filter_build_scope_users_and_sensitive_fields(api, setup):
    remote = setup["remote"]
    valid = remote.builds[0]
    remote.builds += [
        {**valid, "pathType": "download"},
        {**valid, "id": "61", "product": "999"},
        {**valid, "id": "62", "execution": "999"},
        {**valid, "id": "63", "project": "999"},
        {**valid, "id": "64", "deleted": "1"},
    ]
    remote.users += [
        {"id": "2", "account": "gone", "deleted": "1"},
        {"id": "3", "account": "outside", "type": "outside"},
        {"id": "4", "account": "closed"},
        {"id": "5", "account": "guest"},
        {"id": "6", "account": "disabled", "disabled": True},
    ]
    remote.users[0].update(email="private@example.test", resetToken="never-expose")
    result = api.get(setup["url"] + "/options", headers=setup["owner"])
    assert result.status_code == 200, result.text
    data = result.json()["data"]
    assert data["builds"] == [{"id": "trunk", "name": "主干 trunk"}, {"id": "60", "name": "v1.0"}]
    assert data["users"] == [{"account": "dev", "name": "开发甲"}]
    assert "never-expose" not in result.text and "private@example.test" not in result.text
    assert remote.writes == []
    assert set(remote.headers) == {"owner-secret"}


def test_selected_builds_and_remote_account_are_persisted_and_retries_preserve_them(api, setup):
    remote = setup["remote"]
    remote.builds.append({**remote.builds[0], "id": "61", "name": "v1.1"})
    options = api.get(setup["url"] + "/options", headers=setup["owner"]).json()["data"]
    body = {"openedBuild": ["60", "61"], "assignedTo": "dev", "expectedTarget": options["target"]}
    result = dispatch_sync(api, setup, headers=setup["owner"], json=body)
    assert result.json()["data"]["status"] == "succeeded", result.text
    assert remote.writes[0]["payload"]["openedBuild"] == ["60", "61"]
    assert remote.writes[0]["payload"]["assignedTo"] == "dev"
    assert result.json()["data"]["openedBuild"] == ["60", "61"]
    assert result.json()["data"]["assignedTo"] == "dev"
    # No new selection reads or external updates on an already-created Bug.
    previous = len(remote.calls)
    again = dispatch_sync(
        api, setup, headers=setup["owner"], json={"openedBuild": ["999"], "assignedTo": "other"}
    )
    assert again.json()["data"]["openedBuild"] == ["60", "61"]
    assert again.json()["data"]["assignedTo"] == "dev"
    assert len(remote.writes) == 1
    assert not any(name == "put_bugs_bugID" for name, _ in remote.calls[previous:])

    async def snapshot():
        async with api.app.state.test_sessions() as session:
            row = await session.scalar(select(BugZentaoPush))
            assert row.payload_json["assignedTo"] == "dev"
            assert row.payload_json["openedBuild"] == ["60", "61"]

    asyncio.run(snapshot())


@pytest.mark.parametrize(
    "body",
    [
        {"openedBuild": ["999"]},
        {"assignedTo": "gone"},
        {"assignedTo": "1"},
    ],
)
def test_remote_choices_are_revalidated_before_create(api, setup, body):
    result = dispatch_sync(api, setup, headers=setup["owner"], json=body)
    assert result.json()["data"]["latestJob"]["jobStatus"] == "failed", result.text
    assert setup["remote"].writes == []


@pytest.mark.parametrize(
    "body",
    [
        {"openedBuild": []},
        {"openedBuild": ["trunk", "60"]},
        {"openedBuild": ["60", "60"]},
        {"openedBuild": [0]},
        {"openedBuild": ["2147483648"]},
        {"openedBuild": ["../60"]},
        {"assignedTo": "dev\n"},
        {"assignedTo": 1},
        {"unknown": "value"},
    ],
)
def test_invalid_selection_body_is_rejected_without_remote_reads(api, setup, body):
    response = dispatch_sync(api, setup, headers=setup["owner"], json=body)
    assert response.status_code == 400, response.text
    assert setup["remote"].calls == []


def test_options_read_all_pages_with_duplicate_build_rows(api, setup):
    remote = setup["remote"]
    builds = [{**remote.builds[0], "id": str(i), "name": f"v{i}"} for i in range(1, 102)]
    remote.build_pages = {
        1: {
            "builds": [
                row for item in builds[:100] for row in (item, {**item, "pathType": "download"})
            ],
            "pager": {"recTotal": 101},
        },
        2: {"builds": builds[100:], "pager": {"recTotal": 101}},
    }
    remote.user_pages = {
        1: {"users": [{"id": str(i), "account": f"dev{i}"} for i in range(1, 101)], "total": 101},
        2: {"users": [{"id": "101", "account": "last-user"}], "total": 101},
    }
    response = api.get(setup["url"] + "/options", headers=setup["owner"])
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert len(data["builds"]) == 102 and data["builds"][-1]["id"] == "101"
    assert len(data["users"]) == 101
    assert any(user["account"] == "last-user" for user in data["users"])


def test_missing_mcp_paging_capability_is_explicit(api, setup):
    setup["remote"].paging_supported = False
    response = api.get(setup["url"] + "/options", headers=setup["owner"])
    assert response.status_code == 502, response.text
    assert "分页参数" in response.text
    assert setup["remote"].writes == []


def test_repeated_or_incomplete_pages_are_rejected(api, setup):
    remote = setup["remote"]
    remote.build_pages = {
        1: {"builds": remote.builds, "total": 2},
        2: {"builds": remote.builds, "total": 2},
    }
    assert api.get(setup["url"] + "/options", headers=setup["owner"]).status_code == 502
    remote.build_pages[2] = {"builds": [], "total": 2}
    assert api.get(setup["url"] + "/options", headers=setup["owner"]).status_code == 502


def test_stale_target_snapshot_prevents_writing(api, setup):
    options = api.get(setup["url"] + "/options", headers=setup["owner"]).json()["data"]
    options["target"]["instanceUrl"] = "http://other.test"
    response = dispatch_sync(
        api, setup, headers=setup["owner"], json={"expectedTarget": options["target"]}
    )
    assert response.status_code == 409, response.text
    assert setup["remote"].writes == []


def test_options_do_not_borrow_another_members_token(api, setup):
    _, member = account(api, "member")
    assert (
        api.post(
            f"/v1/projects/{setup['pid']}/members",
            headers=setup["owner"],
            json={"name": "member", "role": "member"},
        ).status_code
        == 200
    )
    result = api.get(setup["url"] + "/options", headers=member)
    assert result.status_code == 400, result.text
    assert setup["remote"].calls == []
