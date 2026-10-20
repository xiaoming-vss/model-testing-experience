import json

import httpx
import pytest
from support.function_case_library import make_case, make_suite
from support.project_api import account
from support.zentao_mcp_bindings_api import api as api
from support.zentao_mcp_bindings_api import bind, bind_parents
from support.zentao_mcp_bindings_api import setup as setup

from testing_agent.services.mcp_client import McpClient


@pytest.fixture
def push(api, setup, monkeypatch):
    s = setup
    bind_parents(api, s)
    assert bind(api, s, "requirement", 301).status_code == 200
    suite = make_suite(api, s["owner"], s["req"])
    for title in ("已有用例", "新用例", "第三用例"):
        make_case(
            api,
            s["owner"],
            suite,
            title=title,
            priority="P1",
            content={
                "preconditions": ["已登录"],
                "steps": [{"action": "点击", "expected": "成功"}],
            },
        )
    state = {"mode": "", "writes": [], "tokens": [], "reads": [], "endpoints": []}

    async def handle(request):
        body = json.loads(request.content)
        if body["method"] != "tools/call":
            return await s["remote"].handle(request)
        name, args = body["params"]["name"], body["params"]["arguments"]
        state["tokens"].append(request.headers["token"])
        state["endpoints"].append(str(request.url))
        state["reads"].append(name)
        if name == "get_stories_storyID":
            data = {"story": {"id": "301", "product": "9"}}
        elif name == "get_executions_executionID_testcases":
            data = {"testcases": [{"id": "800", "case": "41"}], "total": 1}
        elif name == "get_testcases_caseID":
            assert str(args["caseID"]) == "41"
            data = {"testcase": {"id": "41", "title": " 已有用例 "}}
        elif name.startswith(("post_", "put_")):
            state["writes"].append((name, args))
            if state["mode"] == "timeout" and name == "post_testcases":
                raise httpx.ReadTimeout("never expose token", request=request)
            if state["mode"] == "403":
                return httpx.Response(403)
            data = {} if name.startswith("put_") else {"id": 42}
        else:
            return await s["remote"].handle(request)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {"structuredContent": {"status": "success", **data}},
            },
        )

    monkeypatch.setattr(
        "testing_agent.services.zentao_mcp_cases.McpClient",
        lambda url, token: McpClient(url, token, transport=httpx.MockTransport(handle)),
    )
    return s, state, f"/v1/function-test-suites/{suite}/zentao/testcases/import"


def test_push_updates_and_creates_without_connector(api, push):
    s, state, url = push
    response = api.post(url, headers=s["owner"], json={"productId": 9, "moduleId": 3})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["importedCaseCount"] == 3 and data["status"] == "success"
    assert set(state["endpoints"]) == {"http://mcp.test/mcp"}
    assert [name for name, _ in state["writes"]] == [
        "put_testcases_testcasID",
        "post_testcases",
        "post_testcases",
    ]
    first, second, third = [args for _, args in state["writes"]]
    assert first["testcasID"] == 41 and third["payload"]["title"] == "第三用例"
    assert second["payload"] == {
        "title": "新用例",
        "module": 3,
        "story": 301,
        "pri": 1,
        "precondition": "已登录",
        "steps": ["点击"],
        "expects": ["成功"],
        "stepType": ["step"],
        "type": "feature",
        "productID": 9,
        "project": 101,
        "execution": 201,
    }
    assert set(state["tokens"]) == {"owner-token"}


def test_partial_write_is_reported_and_timeout_stops_remaining_cases(api, push):
    s, state, url = push
    state["mode"] = "timeout"
    response = api.post(url, headers=s["owner"], json={"productId": 9})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["importedCaseCount"] == 1 and data["status"] == "partial_failure"
    assert [item["status"] for item in data["items"]] == ["success", "uncertain", "skipped"]
    assert len(state["writes"]) == 2
    assert "token" not in response.text


def test_product_and_authorization_rejection_never_write(api, push):
    s, state, url = push
    assert api.post(url, headers=s["owner"], json={"productId": 999}).status_code == 400
    api.delete(s["auth"], headers=s["owner"])
    assert api.post(url, headers=s["owner"], json={"productId": 9}).status_code == 400
    _, outsider = account(api, "outsider")
    assert api.post(url, headers=outsider, json={"productId": 9}).status_code in (403, 404)
    assert not state["writes"]


def test_rejected_write_is_not_counted_as_success(api, push):
    s, state, url = push
    state["mode"] = "403"
    response = api.post(url, headers=s["owner"], json={"productId": 9})
    data = response.json()["data"]
    assert data["importedCaseCount"] == 0
    assert [item["status"] for item in data["items"]] == ["failed", "skipped", "skipped"]
    assert len(state["writes"]) == 1


def test_retired_remote_read_routes_are_unavailable(api, push):
    s, _, _ = push
    for path in ["projects", "executions/201/cases", "executions/201/testtasks"]:
        assert (
            api.get(
                f"/v1/projects/{s['pid']}/integrations/zentao/connections/old/{path}",
                headers=s["owner"],
            ).status_code
            == 404
        )


def test_member_uses_own_mcp_token_and_viewer_cannot_push(api, push):
    s, state, url = push
    for name, role in [("member", "member"), ("viewer", "viewer")]:
        _, headers = account(api, name)
        assert (
            api.post(
                f"/v1/projects/{s['pid']}/members",
                headers=s["owner"],
                json={"name": name, "role": role},
            ).status_code
            == 200
        )
        if role == "member":
            assert api.post(url, headers=headers, json={"productId": 9}).status_code == 400
            api.put(s["auth"], headers=headers, json={"token": "member-token"})
            assert api.post(url, headers=headers, json={"productId": 9}).status_code == 200
            assert set(state["tokens"]) == {"member-token"}
        else:
            before = len(state["writes"])
            assert api.post(url, headers=headers, json={"productId": 9}).status_code == 403
            assert len(state["writes"]) == before


def test_case_push_uses_project_selected_mcp_without_an_operation_selector(api, push):
    from support.zentao_mcp_bindings_api import add_mcp

    s, state, url = push
    sid = add_mcp(api, s)
    root = api.get(f"/v1/projects/{s['pid']}/bindings", headers=s["owner"]).json()["data"]["items"][
        0
    ]
    response = api.patch(
        f"/v1/projects/{s['pid']}/bindings/{root['bindingId']}",
        headers=s["owner"],
        json={"remoteResourceId": "101", "mcpServiceId": sid},
    )
    assert response.status_code == 200, response.text
    response = api.post(url, headers=s["owner"], json={"productId": 9})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["importedCaseCount"] == 3
    assert set(state["endpoints"]) == {"http://second-mcp.test/mcp"}
    assert set(state["tokens"]) == {"second-token"}
