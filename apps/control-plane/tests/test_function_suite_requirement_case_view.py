"""测试集需求-用例视图：用例按生成契约返回，需求与映射只含测试集所属迭代。"""

from test_project_membership_api import account, project
from test_project_membership_api import api as api

REQUIREMENT_CONTENT = "管理员可以在系统配置-服务配置中开启或关闭「启用本地清洗」开关。"


def make_sprint(api, headers, pid, name="iteration"):
    response = api.post(
        f"/v1/projects/{pid}/sprints",
        headers=headers,
        json={
            "name": name,
            "startTime": "2026-09-01T00:00:00Z",
            "endTime": "2026-10-01T00:00:00Z",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["sprintId"]


def make_requirement(api, headers, sprint_id, name="req", **overrides):
    response = api.post(
        f"/v1/sprints/{sprint_id}/requirements", headers=headers, json={"name": name, **overrides}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["requirementId"]


def make_suite(api, headers, requirement_id, name="suite"):
    response = api.post(
        f"/v1/requirements/{requirement_id}/function-test-suites",
        headers=headers,
        json={"name": name},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["suiteId"]


def make_case(api, headers, suite_id, **overrides):
    body = {"title": "case", **overrides}
    response = api.post(f"/v1/function-test-suites/{suite_id}/cases", headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()["data"]["caseId"]


def get_view(api, headers, suite_id):
    response = api.get(
        f"/v1/function-test-suites/{suite_id}/requirement-case-view", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_view_returns_requirement_cases_and_links_in_generation_contract(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid, "迭代A")
    requirement_id = make_requirement(
        api, owner, sprint_id, "本地清洗开关", documentContent=REQUIREMENT_CONTENT
    )
    suite_id = make_suite(api, owner, requirement_id, "系统配置集")
    case_a = make_case(
        api,
        owner,
        suite_id,
        title="开启开关",
        module="系统配置",
        priority="P0",
        caseType="配置相关",
        content={
            "preconditions": ["已以管理员身份登录"],
            "steps": [{"action": "打开开关并保存", "expected": "开关为打开"}],
        },
    )
    case_b = make_case(
        api,
        owner,
        suite_id,
        title="关闭开关",
        module="系统配置",
        priority="P1",
        caseType="配置相关",
        content={
            "preconditions": [],
            "steps": [
                {"action": "关闭开关并保存", "expected": "开关为关闭"},
                {"action": "刷新页面", "expected": "开关保持关闭"},
            ],
        },
    )

    data = get_view(api, owner, suite_id)

    assert [item["requirement_id"] for item in data["requirements"]] == [requirement_id]
    requirement = data["requirements"][0]
    assert requirement["requirement_title"] == "本地清洗开关"
    assert requirement["requirement_content"] == REQUIREMENT_CONTENT

    assert [item["case_id"] for item in data["cases"]] == [case_a, case_b]
    first = data["cases"][0]
    assert first["case_module"] == "系统配置"
    assert first["case_title"] == "开启开关"
    assert first["case_type"] == "配置相关"
    assert first["priority"] == "P0"
    assert first["precondition"] == ["1. 已以管理员身份登录"]
    assert first["test_steps"] == ["1. 打开开关并保存"]
    assert first["expected_results"] == ["1. 开关为打开"]
    second = data["cases"][1]
    assert second["precondition"] == []
    assert second["test_steps"] == ["1. 关闭开关并保存", "2. 刷新页面"]
    assert second["expected_results"] == ["1. 开关为关闭", "2. 开关保持关闭"]

    assert data["case_requirement_links"] == [
        {"requirement_id": requirement_id, "case_ids": [case_a, case_b]}
    ]


def test_view_is_empty_for_suite_without_cases(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    requirement_id = make_requirement(api, owner, make_sprint(api, owner, pid))
    suite_id = make_suite(api, owner, requirement_id)

    data = get_view(api, owner, suite_id)

    assert data == {"requirements": [], "cases": [], "case_requirement_links": []}


def test_view_enforces_project_access(api):
    _, owner = account(api, "owner")
    _, viewer = account(api, "viewer")
    _, outsider = account(api, "outsider")
    pid = project(api, owner)
    requirement_id = make_requirement(api, owner, make_sprint(api, owner, pid))
    suite_id = make_suite(api, owner, requirement_id)
    make_case(api, owner, suite_id, title="可见用例")
    assert (
        api.post(
            f"/v1/projects/{pid}/members", headers=owner, json={"name": "viewer", "role": "viewer"}
        ).status_code
        == 200
    )

    assert get_view(api, viewer, suite_id)["cases"]
    assert (
        api.get(
            f"/v1/function-test-suites/{suite_id}/requirement-case-view", headers=outsider
        ).status_code
        == 403
    )
    assert (
        api.get("/v1/function-test-suites/missing/requirement-case-view", headers=owner).status_code
        == 404
    )
