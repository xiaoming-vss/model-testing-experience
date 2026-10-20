"""Updates to linked Bugs preserve creation and use remote baselines."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from integration_test_driver import dispatch_fields, dispatch_sync, enable
from support.project_api import account
from support.project_api import api as api
from test_bug_zentao_push_api import setup as setup


@pytest.fixture(autouse=True)
def migration_mode(api):
    enable(api)


@pytest.fixture
def linked(api, setup):
    s = setup
    assert dispatch_sync(api, s, headers=s["owner"]).json()["data"]["status"] == "succeeded"
    s.update(
        current_fields={"openedBuild": ["trunk"], "assignedTo": "dev"},
        field_writes=[],
        field_failure="",
        field_apply=True,
        field_entered=threading.Event(),
        field_release=threading.Event(),
        field_block=False,
        on_field_verify=None,
    )
    original = s["remote"].handle

    async def handle(request):
        import json

        body = json.loads(request.content)
        params = body.get("params", {})
        name = params.get("name")
        if name == "put_bugs_bugID":
            args = params["arguments"]
            s["remote"].calls.append((name, args))
            s["remote"].headers.append(request.headers.get("token"))
            s["field_writes"].append(args)
            s["field_entered"].set()
            while s["field_block"] and not s["field_release"].is_set():
                await asyncio.sleep(0.01)
            if s["field_failure"] == "403":
                return httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "id": body["id"],
                        "result": {
                            "content": [
                                {"type": "text", "text": "HTTP 403"},
                                {"type": "text", "text": "{}"},
                            ]
                        },
                    },
                )
            if s["field_apply"]:
                s["current_fields"].update(args["payload"])
            if s["field_failure"] == "timeout":
                raise httpx.ReadTimeout("secret-should-not-leak", request=request)
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {"structuredContent": {"status": "success"}},
                },
            )
        result = await original(request)
        if name == "get_bugs_bugID":
            if s["on_field_verify"]:
                await s["on_field_verify"]()
            if s["field_failure"] == "readback" and s["field_writes"]:
                raise httpx.ReadTimeout("no-readback", request=request)
            payload = result.json()
            payload["result"]["structuredContent"]["bug"].update(product=40, **s["current_fields"])
            return httpx.Response(200, json=payload)
        return result

    s["remote"].handle = handle
    return s


def selection(api, s, **desired):
    result = api.get(s["url"] + "/options", headers=s["owner"])
    assert result.status_code == 200, result.text
    data = result.json()["data"]
    return {
        "openedBuild": data["current"]["openedBuild"],
        "assignedTo": data["current"]["assignedTo"],
        "expectedTarget": data["target"],
        "expectedRemoteBugId": data["current"]["remoteBugId"],
        "expectedOpenedBuild": data["current"]["openedBuild"],
        "expectedAssignedTo": data["current"]["assignedTo"],
        **desired,
    }


def test_existing_options_read_remote_values_and_only_changed_fields_are_updated(api, linked):
    s = linked
    body = selection(api, s, openedBuild=["60"])
    result = dispatch_fields(api, s, headers=s["owner"], json=body)
    assert result.status_code == 200, result.text
    data = result.json()["data"]
    assert data["status"] == "succeeded" and data["remoteBugId"] == 50
    assert data["fieldUpdateStatus"] == "succeeded"
    assert s["field_writes"] == [{"bugID": 50, "payload": {"openedBuild": ["60"]}}]
    assert s["current_fields"] == {"openedBuild": ["60"], "assignedTo": "dev"}
    assert len(s["remote"].writes) == 1
    records = api.get(f"/v1/bugs/{s['bug']['bugId']}/activities", headers=s["owner"]).json()[
        "data"
    ]["items"]
    assert len([item for item in records if item["action"] == "zentao_fields_update"]) == 1
    assert (
        api.get("/v1/bugs/" + s["bug"]["bugId"], headers=s["owner"]).json()["data"][
            "assigneeUserId"
        ]
        == s["bug"]["assigneeUserId"]
    )


def test_updates_account_and_can_explicitly_clear_assignment(api, linked):
    s = linked
    s["current_fields"]["assignedTo"] = "old-unavailable"
    body = selection(api, s, assignedTo="dev")
    result = dispatch_fields(api, s, headers=s["owner"], json=body)
    assert result.json()["data"]["fieldUpdateStatus"] == "succeeded", result.text
    assert s["field_writes"][-1]["payload"] == {"assignedTo": "dev"}
    result = dispatch_fields(api, s, headers=s["owner"], json=selection(api, s, assignedTo=""))
    assert result.json()["data"]["fieldUpdateStatus"] == "succeeded", result.text
    assert s["field_writes"][-1]["payload"] == {"assignedTo": ""}


def test_unchanged_remote_legacy_values_are_preserved_when_editing_other_field(api, linked):
    s = linked
    s["current_fields"] = {"openedBuild": ["999"], "assignedTo": "closed"}
    body = selection(api, s, openedBuild=["60"])
    result = dispatch_fields(api, s, headers=s["owner"], json=body)
    assert result.json()["data"]["fieldUpdateStatus"] == "succeeded", result.text
    assert s["field_writes"][-1]["payload"] == {"openedBuild": ["60"]}


def test_unchanged_save_does_not_write_or_create_again(api, linked):
    s = linked
    result = dispatch_fields(api, s, headers=s["owner"], json=selection(api, s))
    assert result.status_code == 200, result.text
    assert s["field_writes"] == [] and len(s["remote"].writes) == 1


@pytest.mark.parametrize("change", ["baseline", "bug", "instance", "invalid-user", "invalid-build"])
def test_stale_or_invalid_field_update_is_rejected_before_write(api, linked, change):
    s = linked
    body = selection(api, s, openedBuild=["60"])
    if change == "baseline":
        s["current_fields"]["assignedTo"] = "changed-by-other-user"
    elif change == "bug":
        body["expectedRemoteBugId"] = 999
    elif change == "instance":
        body["expectedTarget"]["instanceUrl"] = "http://other.test"
    elif change == "invalid-user":
        body["assignedTo"] = "missing"
    else:
        body["openedBuild"] = ["999"]
    result = dispatch_fields(api, s, headers=s["owner"], json=body)
    if change in {"baseline", "invalid-user", "invalid-build"}:
        assert result.status_code == 200
        assert result.json()["data"]["latestJob"]["jobStatus"] == "failed"
    else:
        assert result.status_code in {400, 409}, result.text
    assert s["field_writes"] == []
    assert len(s["remote"].writes) == 1


@pytest.mark.parametrize("failure", ["timeout", "readback"])
def test_uncertain_update_is_recovered_by_readback_without_repeating_the_write(
    api, linked, failure
):
    s = linked
    body = selection(api, s, openedBuild=["60"])
    s["field_failure"] = failure
    result = dispatch_fields(api, s, headers=s["owner"], json=body)
    assert result.json()["data"]["fieldUpdateStatus"] == "unknown", result.text
    assert result.json()["data"]["status"] == "succeeded"
    s["field_failure"] = ""
    current = api.get(s["url"] + "/options", headers=s["owner"])
    assert current.status_code == 200, current.text
    assert current.json()["data"]["current"]["openedBuild"] == ["60"]
    assert api.get(s["url"], headers=s["owner"]).json()["data"]["fieldUpdateStatus"] == "succeeded"
    assert len(s["field_writes"]) == 1 and len(s["remote"].writes) == 1


def test_unknown_result_cannot_be_blindly_retried(api, linked):
    s = linked
    body = selection(api, s, openedBuild=["60"])
    s["field_failure"], s["field_apply"] = "timeout", False
    result = dispatch_fields(api, s, headers=s["owner"], json=body)
    assert result.json()["data"]["fieldUpdateStatus"] == "unknown", result.text
    assert dispatch_fields(api, s, headers=s["owner"], json=body).status_code == 409
    assert api.get(s["url"] + "/options", headers=s["owner"]).status_code == 409
    assert len(s["field_writes"]) == 1


def test_known_failure_preserves_creation_and_can_retry(api, linked):
    s = linked
    body = selection(api, s, openedBuild=["60"])
    s["field_failure"] = "403"
    result = dispatch_fields(api, s, headers=s["owner"], json=body)
    assert result.json()["data"]["fieldUpdateStatus"] == "failed", result.text
    assert result.json()["data"]["status"] == "succeeded"
    s["field_failure"] = ""
    result = dispatch_fields(api, s, headers=s["owner"], json=selection(api, s, openedBuild=["60"]))
    assert result.json()["data"]["fieldUpdateStatus"] == "succeeded", result.text
    assert len(s["remote"].writes) == 1


def test_concurrent_updates_do_not_send_a_second_write(api, linked):
    s = linked
    body = selection(api, s, openedBuild=["60"])
    s["field_block"] = True
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(dispatch_fields, api, s, headers=s["owner"], json=body)
        assert s["field_entered"].wait(timeout=10)
        try:
            second = workers.submit(dispatch_fields, api, s, headers=s["owner"], json=body)
            assert second.result(timeout=10).status_code == 409
        finally:
            s["field_release"].set()
        assert first.result(timeout=10).json()["data"]["fieldUpdateStatus"] == "succeeded"
    assert len(s["field_writes"]) == 1


def test_members_cannot_borrow_the_original_pushers_token(api, linked):
    _, member = account(api, "member")
    assert (
        api.post(
            f"/v1/projects/{linked['pid']}/members",
            headers=linked["owner"],
            json={"name": "member", "role": "member"},
        ).status_code
        == 200
    )
    assert api.get(linked["url"] + "/options", headers=member).status_code == 400
    assert linked["field_writes"] == []


def test_authorization_revoked_during_baseline_read_prevents_update(api, linked):
    from sqlalchemy import update

    from testing_agent.models.integration_connection import IntegrationConnection

    s = linked
    body = selection(api, s, openedBuild=["60"])
    count = 0

    async def revoke():
        nonlocal count
        count += 1
        if count == 2:
            async with api.app.state.test_sessions() as session:
                await session.execute(
                    update(IntegrationConnection)
                    .where(IntegrationConnection.provider == "mcp")
                    .values(status="invalid")
                )
                from testing_agent.services.worker_authorization import revoke_executions

                await revoke_executions(session, actor=s["bug"]["reporterUserId"])
                await session.commit()

    s["on_field_verify"] = revoke
    result = dispatch_fields(api, s, headers=s["owner"], json=body)
    assert result.json()["data"]["latestJob"]["jobStatus"] == "canceled", result.text
    assert s["field_writes"] == []


def test_instance_switch_waits_for_active_field_update(api, linked):
    s = linked
    body = selection(api, s, openedBuild=["60"])
    s["field_block"] = True
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(dispatch_fields, api, s, headers=s["owner"], json=body)
        assert s["field_entered"].wait(timeout=10)
        try:
            s["remote"].instance = "http://new-zen.test"
            result = api.patch(
                f"{s['path']}/{s['sid']}",
                headers=s["owner"],
                json={
                    "name": "ZenTao-MCP",
                    "baseUrl": "http://next-mcp.test/zentao/mcp",
                    "confirmInstanceSwitch": True,
                },
            )
            assert result.status_code == 409, result.text
            assert "集成写入正在执行" in result.text
        finally:
            s["remote"].instance = "http://zentao.test"
            s["field_release"].set()
        assert first.result(timeout=10).json()["data"]["fieldUpdateStatus"] == "succeeded"
    assert len(s["remote"].writes) == 1


def test_explicit_success_with_normalized_values_reports_failure_and_can_reload(api, linked):
    s = linked
    body = selection(api, s, openedBuild=["60"])
    s["field_apply"] = False
    result = dispatch_fields(api, s, headers=s["owner"], json=body)
    assert result.json()["data"]["fieldUpdateStatus"] == "failed", result.text
    assert result.json()["data"]["openedBuild"] == ["trunk"]
    assert api.get(s["url"] + "/options", headers=s["owner"]).status_code == 200
    assert len(s["field_writes"]) == 1 and len(s["remote"].writes) == 1
