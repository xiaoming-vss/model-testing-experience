"""测试单图谱输入：本迭代需求的用例、需求与关联，可直接作为派发的 graphInput。"""

from test_function_case_library import make_case, make_requirement, make_sprint, make_suite
from test_project_membership_api import account, project
from test_project_membership_api import api as api
from test_test_order_api import make_order, seed_case

REQUIREMENT_CONTENT = "管理员可以在系统配置-服务配置中开启或关闭「启用本地清洗」开关。"


def add_cases(api, headers, order_id, case_ids):
    response = api.post(
        f"/v1/test-orders/{order_id}/cases", headers=headers, json={"caseIds": case_ids}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def make_requirement_with_content(api, headers, sprint_id, name, content):
    """带文本正文的需求；正文接口与图谱输入之间要能对上。"""
    response = api.post(
        f"/v1/sprints/{sprint_id}/requirements",
        headers=headers,
        json={"name": name, "documentContent": content},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["requirementId"]


def graph_input(api, headers, order_id):
    response = api.get(f"/v1/test-orders/{order_id}/graph-input", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_graph_input_returns_order_cases_requirements_and_links(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid, "迭代A")
    requirement_id = make_requirement_with_content(
        api, owner, sprint_id, "本地清洗开关", REQUIREMENT_CONTENT
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
            "steps": [
                {"action": "打开开关并保存", "expected": "开关为打开"},
                {"action": "刷新页面", "expected": "开关保持打开"},
            ],
        },
    )
    case_b = make_case(api, owner, suite_id, title="关闭开关", module="系统配置")
    order = make_order(api, owner, sprint_id, name="V1.2 回归")
    add_cases(api, owner, order["orderId"], [case_a, case_b])

    data = graph_input(api, owner, order["orderId"])

    assert data["requirements"] == [
        {
            "requirement_id": requirement_id,
            "requirement_title": "本地清洗开关",
            "requirement_content": REQUIREMENT_CONTENT,
        }
    ]
    assert [case["case_id"] for case in data["cases"]] == [case_a, case_b]
    first = data["cases"][0]
    # 字段名与 worker 侧 skill 的输入契约一致：snake_case，不是 camelCase。
    assert set(first) == {
        "case_id",
        "case_module",
        "case_title",
        "case_type",
        "priority",
        "precondition",
        "test_steps",
        "expected_results",
    }
    assert first["case_module"] == "系统配置"
    assert first["case_title"] == "开启开关"
    assert first["case_type"] == "配置相关"
    assert first["priority"] == "P0"
    # 正文来自条目快照，按生成契约重新编号。
    assert first["precondition"] == ["1. 已以管理员身份登录"]
    assert first["test_steps"] == ["1. 打开开关并保存", "2. 刷新页面"]
    assert first["expected_results"] == ["1. 开关为打开", "2. 开关保持打开"]
    assert data["case_requirement_links"] == [
        {"requirement_id": requirement_id, "case_ids": [case_a, case_b]}
    ]


def test_graph_input_keeps_unbound_cases_under_null_requirement(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_a = make_sprint(api, owner, pid, "迭代A")
    sprint_b = make_sprint(api, owner, pid, "迭代B")
    requirement_a = make_requirement(api, owner, sprint_a, "本迭代需求")
    requirement_b = make_requirement(api, owner, sprint_b, "别的迭代需求")
    requirement_c = make_requirement(api, owner, sprint_b, "别的迭代另一个需求")
    case_a = seed_case(api, owner, requirement_a, title="本迭代用例")
    case_b = seed_case(api, owner, requirement_b, title="别的迭代用例")
    case_c = seed_case(api, owner, requirement_c, title="别的迭代另一个用例")
    order = make_order(api, owner, sprint_a, name="V1.2 回归")
    # 加用例只校验项目归属，跨迭代的用例可以进同一张测试单。
    add_cases(api, owner, order["orderId"], [case_a, case_b, case_c])

    data = graph_input(api, owner, order["orderId"])

    # 用例全部保留；只有绑定本迭代需求的才进 requirements。
    assert [case["case_id"] for case in data["cases"]] == [case_a, case_b, case_c]
    assert [item["requirement_id"] for item in data["requirements"]] == [requirement_a]
    # 组内保持条目加入顺序；所有未绑定本迭代需求的用例合并成同一个 null 分组。
    assert data["case_requirement_links"] == [
        {"requirement_id": requirement_a, "case_ids": [case_a]},
        {"requirement_id": None, "case_ids": [case_b, case_c]},
    ]


def test_graph_input_groups_cases_by_requirement(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid, "迭代A")
    requirement_a = make_requirement(api, owner, sprint_id, "需求A")
    requirement_b = make_requirement(api, owner, sprint_id, "需求B")
    case_a1 = seed_case(api, owner, requirement_a, title="A1")
    case_a2 = seed_case(api, owner, requirement_a, title="A2")
    case_b1 = seed_case(api, owner, requirement_b, title="B1")
    order = make_order(api, owner, sprint_id, name="V1.2 回归")
    add_cases(api, owner, order["orderId"], [case_a1, case_b1, case_a2])

    data = graph_input(api, owner, order["orderId"])

    assert [item["requirement_id"] for item in data["requirements"]] == [
        requirement_a,
        requirement_b,
    ]
    # 关联按需求归组，组内保持条目加入顺序。
    assert data["case_requirement_links"] == [
        {"requirement_id": requirement_a, "case_ids": [case_a1, case_a2]},
        {"requirement_id": requirement_b, "case_ids": [case_b1]},
    ]


def test_graph_input_keeps_existing_step_numbering(api):
    """被压成单步的旧数据：正文自带序号时不再叠加，避免返回「1. 1. …」。"""
    _, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid, "迭代A")
    requirement_id = make_requirement(api, owner, sprint_id, "需求")
    suite_id = make_suite(api, owner, requirement_id, "用例集")
    case_id = make_case(
        api,
        owner,
        suite_id,
        title="压缩步骤的用例",
        content={
            "preconditions": ["1. 已准备好环境"],
            "steps": [{"action": "1. 第一步\n2. 第二步", "expected": "1. 预期一\n2. 预期二"}],
        },
    )
    order = make_order(api, owner, sprint_id, name="V1.2 回归")
    add_cases(api, owner, order["orderId"], [case_id])

    data = graph_input(api, owner, order["orderId"])

    assert data["cases"][0]["precondition"] == ["1. 已准备好环境"]
    assert data["cases"][0]["test_steps"] == ["1. 第一步\n2. 第二步"]
    assert data["cases"][0]["expected_results"] == ["1. 预期一\n2. 预期二"]


def test_graph_input_is_empty_for_order_without_cases(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid, "迭代A")
    make_requirement(api, owner, sprint_id, "需求")
    order = make_order(api, owner, sprint_id, name="空单")

    assert graph_input(api, owner, order["orderId"]) == {
        "requirements": [],
        "cases": [],
        "case_requirement_links": [],
    }


def test_graph_input_enforces_project_access(api):
    _, owner = account(api, "owner")
    _, outsider = account(api, "outsider")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid, "迭代A")
    order = make_order(api, owner, sprint_id, name="V1.2 回归")

    assert (
        api.get(f"/v1/test-orders/{order['orderId']}/graph-input", headers=outsider).status_code
        == 403
    )
    assert api.get("/v1/test-orders/missing/graph-input", headers=owner).status_code == 404
