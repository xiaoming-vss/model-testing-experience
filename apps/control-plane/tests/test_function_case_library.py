"""用例库：项目范围内的用例检索（服务端筛选 + 分页）与项目级测试集列表。"""

from urllib.parse import urlencode

from test_project_membership_api import account, project
from test_project_membership_api import api as api

SPRINT_BODY = {
    "name": "iteration",
    "startTime": "2026-09-01T00:00:00Z",
    "endTime": "2026-10-01T00:00:00Z",
}


def make_sprint(api, headers, pid, name="iteration"):
    response = api.post(
        f"/v1/projects/{pid}/sprints", headers=headers, json={**SPRINT_BODY, "name": name}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["sprintId"]


def make_requirement(api, headers, sprint_id, name="req"):
    response = api.post(
        f"/v1/sprints/{sprint_id}/requirements", headers=headers, json={"name": name}
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


def list_library(api, headers, pid, **params):
    query = urlencode({key: value for key, value in params.items() if value not in ("", None)})
    suffix = f"?{query}" if query else ""
    response = api.get(f"/v1/projects/{pid}/function-test-cases{suffix}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_library_lists_cases_across_requirements_with_scope_names(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_a = make_sprint(api, owner, pid, "迭代A")
    sprint_b = make_sprint(api, owner, pid, "迭代B")
    req_a = make_requirement(api, owner, sprint_a, "需求A")
    req_b = make_requirement(api, owner, sprint_b, "需求B")
    suite_a = make_suite(api, owner, req_a, "登录集")
    suite_b = make_suite(api, owner, req_b, "支付集")
    case_a = make_case(
        api,
        owner,
        suite_a,
        title="登录成功",
        module="登录",
        priority="P0",
        caseType="功能测试",
        content={
            "preconditions": ["已注册"],
            "steps": [{"action": "输入验证码", "expected": "登录成功"}],
        },
    )
    case_b = make_case(api, owner, suite_b, title="下单支付")

    data = list_library(api, owner, pid)
    assert data["total"] == 2
    by_id = {item["caseId"]: item for item in data["items"]}
    assert set(by_id) == {case_a, case_b}

    item = by_id[case_a]
    assert item["suiteName"] == "登录集"
    assert item["requirementId"] == req_a
    assert item["requirementName"] == "需求A"
    assert item["sprintId"] == sprint_a
    assert item["sprintName"] == "迭代A"
    assert item["content"]["preconditions"] == ["已注册"]
    assert item["content"]["steps"][0]["action"] == "输入验证码"
    assert item["title"] == "登录成功"
    assert item["module"] == "登录"
    assert item["priority"] == "P0"
    assert item["caseType"] == "功能测试"
    assert by_id[case_b]["sprintName"] == "迭代B"


def test_library_filters_by_sprint_requirement_and_suite(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_a = make_sprint(api, owner, pid, "迭代A")
    sprint_b = make_sprint(api, owner, pid, "迭代B")
    req_a = make_requirement(api, owner, sprint_a, "需求A")
    req_b = make_requirement(api, owner, sprint_b, "需求B")
    suite_a = make_suite(api, owner, req_a, "登录集")
    suite_b = make_suite(api, owner, req_b, "支付集")
    make_case(api, owner, suite_a, title="A1")
    make_case(api, owner, suite_a, title="A2")
    make_case(api, owner, suite_b, title="B1")

    assert list_library(api, owner, pid, sprintId=sprint_a)["total"] == 2
    assert list_library(api, owner, pid, sprintId=sprint_b)["total"] == 1
    assert list_library(api, owner, pid, requirementId=req_b)["total"] == 1
    assert list_library(api, owner, pid, suiteId=suite_a)["total"] == 2
    assert list_library(api, owner, pid, sprintId=sprint_b, suiteId=suite_a)["total"] == 0


def test_library_filters_by_module_priority_case_type_and_keyword(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    requirement_id = make_requirement(api, owner, make_sprint(api, owner, pid))
    suite_id = make_suite(api, owner, requirement_id)
    make_case(
        api, owner, suite_id, title="登录成功", module="登录", priority="P0", caseType="功能测试"
    )
    make_case(
        api,
        owner,
        suite_id,
        title="退款拦截",
        module="退款",
        priority="P1",
        caseType="异常测试",
        content={
            "preconditions": [],
            "steps": [{"action": "提交超额退款", "expected": "提示超出可退金额"}],
        },
    )

    assert list_library(api, owner, pid, module="登录")["total"] == 1
    assert list_library(api, owner, pid, priority="P1")["total"] == 1
    assert list_library(api, owner, pid, caseType="异常测试")["total"] == 1
    assert list_library(api, owner, pid, keyword="登录")["total"] == 1
    assert list_library(api, owner, pid, keyword="退款")["total"] == 1
    assert list_library(api, owner, pid, keyword="退")["total"] == 1
    # 关键字只检索标题与模块这两个真实文本列；用例正文存在 JSON 列里，
    # 跨方言（MySQL 规范化 JSON / SQLite 转义文本）无法可靠检索，故不支持。
    assert list_library(api, owner, pid, keyword="超出可退金额")["total"] == 0
    assert list_library(api, owner, pid, keyword="查无此词")["total"] == 0


def test_library_paginates_with_total_and_stable_pages(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    requirement_id = make_requirement(api, owner, make_sprint(api, owner, pid))
    suite_id = make_suite(api, owner, requirement_id)
    for index in range(5):
        make_case(api, owner, suite_id, title=f"用例{index}")

    first = list_library(api, owner, pid, page=1, pageSize=2)
    second = list_library(api, owner, pid, page=2, pageSize=2)
    third = list_library(api, owner, pid, page=3, pageSize=2)
    assert (first["total"], second["total"], third["total"]) == (5, 5, 5)
    assert [len(page["items"]) for page in (first, second, third)] == [2, 2, 1]
    seen = [item["caseId"] for page in (first, second, third) for item in page["items"]]
    assert len(set(seen)) == 5


def test_library_is_scoped_to_one_project_and_rejects_invalid_paging(api):
    _, owner = account(api, "owner")
    pid = project(api, owner, "本项目")
    other = project(api, owner, "另一个项目")
    requirement_id = make_requirement(api, owner, make_sprint(api, owner, pid))
    make_case(api, owner, make_suite(api, owner, requirement_id), title="本项目用例")
    other_requirement = make_requirement(api, owner, make_sprint(api, owner, other))
    make_case(api, owner, make_suite(api, owner, other_requirement), title="别的项目用例")

    data = list_library(api, owner, pid)
    assert [item["title"] for item in data["items"]] == ["本项目用例"]
    assert (
        api.get(f"/v1/projects/{pid}/function-test-cases?page=0", headers=owner).status_code == 400
    )
    assert (
        api.get(f"/v1/projects/{pid}/function-test-cases?pageSize=500", headers=owner).status_code
        == 400
    )


def test_library_enforces_project_access(api):
    _, owner = account(api, "owner")
    _, viewer = account(api, "viewer")
    _, outsider = account(api, "outsider")
    pid = project(api, owner)
    requirement_id = make_requirement(api, owner, make_sprint(api, owner, pid))
    make_case(api, owner, make_suite(api, owner, requirement_id), title="可见用例")
    assert (
        api.post(
            f"/v1/projects/{pid}/members", headers=owner, json={"name": "viewer", "role": "viewer"}
        ).status_code
        == 200
    )

    assert list_library(api, viewer, pid)["total"] == 1
    assert api.get(f"/v1/projects/{pid}/function-test-cases", headers=outsider).status_code == 403
    assert api.get("/v1/projects/missing/function-test-cases", headers=owner).status_code == 404


def test_project_suite_list_covers_every_requirement_with_case_counts(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_a = make_sprint(api, owner, pid, "迭代A")
    sprint_b = make_sprint(api, owner, pid, "迭代B")
    req_a = make_requirement(api, owner, sprint_a, "需求A")
    req_b = make_requirement(api, owner, sprint_b, "需求B")
    suite_a = make_suite(api, owner, req_a, "登录集")
    suite_b = make_suite(api, owner, req_b, "支付集")
    make_case(api, owner, suite_a, title="A1")
    make_case(api, owner, suite_b, title="B1")

    response = api.get(f"/v1/projects/{pid}/function-test-suites", headers=owner)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 2
    counts = {item["suiteId"]: item["caseCount"] for item in data["items"]}
    assert counts == {suite_a: 1, suite_b: 1}

    filtered = api.get(
        f"/v1/projects/{pid}/function-test-suites?{urlencode({'sprintId': sprint_b})}",
        headers=owner,
    ).json()["data"]
    assert [item["suiteId"] for item in filtered["items"]] == [suite_b]
