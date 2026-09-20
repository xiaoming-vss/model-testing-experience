"""测试单与执行条目：创建、加用例、快照、进度推导、删除链、权限与执行人分配。"""

from datetime import UTC, datetime

import pytest
from test_ai_execution_storage import AsyncSessionAdapter
from test_ai_execution_storage import db as db
from test_function_case_library import make_case, make_requirement, make_sprint, make_suite
from test_project_membership_api import account, project
from test_project_membership_api import api as api

from testing_agent.core.errors import AppError
from testing_agent.domain.test_order_status import derive_test_order_status

# 这些类型的名字以 Test 开头，按模块引入可避免 pytest 把它们当测试类收集。
from testing_agent.models import test_order as test_order_models
from testing_agent.models import test_order_entry as test_order_entry_models
from testing_agent.models.project import Project
from testing_agent.models.sprint import Sprint
from testing_agent.repositories import test_order as test_order_repositories
from testing_agent.repositories import test_order_entry as test_order_entry_repositories
from testing_agent.repositories.sprint_daily_metrics import SprintDailyMetricsRepository
from testing_agent.schemas import test_order as test_order_schemas
from testing_agent.services import test_order as test_order_services
from testing_agent.services import test_order_entry as test_order_entry_services
from testing_agent.services.sprint_daily_metrics import SprintDailyMetricsService


def make_order(api, headers, sprint_id, name="测试单", tested_version="V1.0.0"):
    response = api.post(
        f"/v1/sprints/{sprint_id}/test-orders",
        headers=headers,
        json={"name": name, "testedVersion": tested_version},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def seed_case(api, headers, requirement_id, title="登录成功", **overrides):
    suite_id = make_suite(api, headers, requirement_id, name=f"{title}集")
    return make_case(api, headers, suite_id, title=title, **overrides)


def entries_of(api, headers, order_id):
    response = api.get(f"/v1/test-orders/{order_id}/entries", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_creates_test_order_in_iteration_and_rejects_duplicate_name(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_a = make_sprint(api, owner, pid, "迭代A")
    sprint_b = make_sprint(api, owner, pid, "迭代B")

    order = make_order(api, owner, sprint_a, name="V2.3 回归", tested_version="V2.3.1-rc2")
    assert order["projectId"] == pid
    assert order["sprintId"] == sprint_a
    assert order["testedVersion"] == "V2.3.1-rc2"
    assert order["entriesTotal"] == 0
    assert order["status"] == "pending"

    duplicate = api.post(
        f"/v1/sprints/{sprint_a}/test-orders",
        headers=owner,
        json={"name": "V2.3 回归"},
    )
    assert duplicate.status_code == 409, duplicate.text
    # 同名可以出现在另一个迭代下
    assert (
        api.post(
            f"/v1/sprints/{sprint_b}/test-orders", headers=owner, json={"name": "V2.3 回归"}
        ).status_code
        == 200
    )


def test_adds_library_cases_as_entries_with_a_snapshot(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid)
    requirement_id = make_requirement(api, owner, sprint_id)
    case_id = seed_case(
        api,
        owner,
        requirement_id,
        module="登录",
        priority="P0",
        content={
            "preconditions": ["已注册"],
            "steps": [{"action": "输入验证码", "expected": "登录成功"}],
        },
    )
    order = make_order(api, owner, sprint_id)

    added = api.post(
        f"/v1/test-orders/{order['orderId']}/cases", headers=owner, json={"caseIds": [case_id]}
    )
    assert added.status_code == 200, added.text
    assert added.json()["data"] == {"addedCount": 1, "skippedCount": 0}

    data = entries_of(api, owner, order["orderId"])
    assert data["total"] == 1
    entry = data["items"][0]
    assert entry["caseType"] == "function"
    assert entry["caseId"] == case_id
    assert entry["status"] == "pending"
    assert entry["caseTitle"] == "登录成功"
    assert entry["caseModule"] == "登录"
    assert entry["casePriority"] == "P0"
    assert entry["snapshot"]["preconditions"] == ["已注册"]
    assert entry["snapshot"]["steps"][0]["action"] == "输入验证码"

    # 用例内容改动不影响已加入条目的快照
    patched = api.patch(
        f"/v1/function-test-cases/{case_id}",
        headers=owner,
        json={
            "title": "改过的标题",
            "content": {
                "preconditions": ["改过"],
                "steps": [{"action": "改过", "expected": "改过"}],
            },
        },
    )
    assert patched.status_code == 200, patched.text
    entry_after = entries_of(api, owner, order["orderId"])["items"][0]
    assert entry_after["snapshot"]["preconditions"] == ["已注册"]
    assert entry_after["snapshot"]["steps"][0]["action"] == "输入验证码"
    assert entry_after["caseTitle"] == "改过的标题"


def test_project_list_filters_by_iteration_and_reports_progress(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_a = make_sprint(api, owner, pid, "迭代A")
    sprint_b = make_sprint(api, owner, pid, "迭代B")
    requirement_a = make_requirement(api, owner, sprint_a)
    requirement_b = make_requirement(api, owner, sprint_b)
    order_a = make_order(api, owner, sprint_a, name="A单")
    order_b = make_order(api, owner, sprint_b, name="B单")
    case_a = seed_case(api, owner, requirement_a, title="A用例")
    case_b = seed_case(api, owner, requirement_b, title="B用例")
    assert (
        api.post(
            f"/v1/test-orders/{order_a['orderId']}/cases", headers=owner, json={"caseIds": [case_a]}
        ).status_code
        == 200
    )
    assert (
        api.post(
            f"/v1/test-orders/{order_b['orderId']}/cases", headers=owner, json={"caseIds": [case_b]}
        ).status_code
        == 200
    )

    listing = api.get(f"/v1/projects/{pid}/test-orders", headers=owner).json()["data"]
    assert listing["total"] == 2
    by_name = {item["name"]: item for item in listing["items"]}
    assert by_name["A单"]["entriesTotal"] == 1
    assert by_name["A单"]["entriesExecuted"] == 0
    assert by_name["A单"]["entriesPassed"] == 0
    assert by_name["A单"]["status"] == "pending"

    filtered = api.get(f"/v1/projects/{pid}/test-orders?sprintId={sprint_b}", headers=owner).json()[
        "data"
    ]
    assert [item["orderId"] for item in filtered["items"]] == [order_b["orderId"]]


def test_add_is_idempotent_and_rejects_foreign_or_missing_cases(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    other = project(api, owner, "另一个项目")
    sprint_id = make_sprint(api, owner, pid)
    requirement_id = make_requirement(api, owner, sprint_id)
    case_id = seed_case(api, owner, requirement_id)
    other_case = seed_case(
        api,
        owner,
        make_requirement(api, owner, make_sprint(api, owner, other)),
        title="别的项目用例",
    )
    order = make_order(api, owner, sprint_id)

    first = api.post(
        f"/v1/test-orders/{order['orderId']}/cases", headers=owner, json={"caseIds": [case_id]}
    )
    assert first.json()["data"] == {"addedCount": 1, "skippedCount": 0}
    second = api.post(
        f"/v1/test-orders/{order['orderId']}/cases",
        headers=owner,
        json={"caseIds": [case_id, case_id]},
    )
    assert second.json()["data"] == {"addedCount": 0, "skippedCount": 1}
    assert entries_of(api, owner, order["orderId"])["total"] == 1

    foreign = api.post(
        f"/v1/test-orders/{order['orderId']}/cases", headers=owner, json={"caseIds": [other_case]}
    )
    assert foreign.status_code == 400, foreign.text
    missing = api.post(
        f"/v1/test-orders/{order['orderId']}/cases", headers=owner, json={"caseIds": ["nope"]}
    )
    assert missing.status_code == 404, missing.text


def test_removes_entry_and_cascades_when_the_case_is_deleted(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid)
    requirement_id = make_requirement(api, owner, sprint_id)
    case_a = seed_case(api, owner, requirement_id, title="A")
    case_b = seed_case(api, owner, requirement_id, title="B")
    order = make_order(api, owner, sprint_id)
    api.post(
        f"/v1/test-orders/{order['orderId']}/cases",
        headers=owner,
        json={"caseIds": [case_a, case_b]},
    )
    entries = entries_of(api, owner, order["orderId"])["items"]
    assert [entry["caseTitle"] for entry in entries] == ["A", "B"]

    removed = api.delete(
        f"/v1/test-orders/{order['orderId']}/entries/{entries[0]['entryId']}", headers=owner
    )
    assert removed.status_code == 200, removed.text
    remaining = entries_of(api, owner, order["orderId"])
    assert [entry["caseTitle"] for entry in remaining["items"]] == ["B"]
    assert (
        api.get(f"/v1/test-orders/{order['orderId']}", headers=owner).json()["data"]["entriesTotal"]
        == 1
    )

    # 删除用例会级联删除引用它的条目
    assert api.delete(f"/v1/function-test-cases/{case_b}", headers=owner).status_code == 200
    assert entries_of(api, owner, order["orderId"])["total"] == 0


def test_deleting_iteration_with_test_orders_is_blocked(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid)
    make_order(api, owner, sprint_id, name="待清理测试单")

    blocked = api.delete(f"/v1/sprints/{sprint_id}", headers=owner)
    assert blocked.status_code == 409, blocked.text
    assert "test_orders" in {item["resource"] for item in blocked.json()["data"]["blockers"]}


def test_viewer_reads_test_orders_but_cannot_change_them(api):
    _, owner = account(api, "owner")
    _, viewer = account(api, "viewer")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid)
    requirement_id = make_requirement(api, owner, sprint_id)
    case_id = seed_case(api, owner, requirement_id)
    order = make_order(api, owner, sprint_id)
    assert (
        api.post(
            f"/v1/projects/{pid}/members", headers=owner, json={"name": "viewer", "role": "viewer"}
        ).status_code
        == 200
    )

    assert api.get(f"/v1/test-orders/{order['orderId']}", headers=viewer).status_code == 200
    assert entries_of(api, viewer, order["orderId"])["total"] == 0
    assert (
        api.post(
            f"/v1/sprints/{sprint_id}/test-orders", headers=viewer, json={"name": "viewer 的单"}
        ).status_code
        == 403
    )
    assert (
        api.post(
            f"/v1/test-orders/{order['orderId']}/cases", headers=viewer, json={"caseIds": [case_id]}
        ).status_code
        == 403
    )
    assert api.delete(f"/v1/test-orders/{order['orderId']}", headers=viewer).status_code == 403


def test_order_status_is_derived_from_entry_results():
    assert derive_test_order_status(0, 0) == "pending"
    assert derive_test_order_status(3, 0) == "pending"
    assert derive_test_order_status(3, 2) == "in_progress"
    assert derive_test_order_status(3, 3) == "completed"


def test_owner_assigns_executor_and_others_cannot(api):
    _, owner = account(api, "owner")
    member_user, member = account(api, "member")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid)
    requirement_id = make_requirement(api, owner, sprint_id)
    case_id = seed_case(api, owner, requirement_id)
    order = make_order(api, owner, sprint_id)
    api.post(
        f"/v1/test-orders/{order['orderId']}/cases", headers=owner, json={"caseIds": [case_id]}
    )
    entry = entries_of(api, owner, order["orderId"])["items"][0]
    assert entry["assigneeUserId"] == ""
    assert (
        api.post(
            f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
        ).status_code
        == 200
    )

    url = f"/v1/test-orders/{order['orderId']}/entries/assign"
    assigned = api.post(
        url,
        headers=owner,
        json={"entryIds": [entry["entryId"]], "assigneeUserId": member_user["userId"]},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["data"]["items"][0]["assigneeUserId"] == member_user["userId"]
    assert (
        entries_of(api, owner, order["orderId"])["items"][0]["assigneeUserId"]
        == member_user["userId"]
    )

    # 普通成员没有 manage，不能分配
    assert (
        api.post(
            url, headers=member, json={"entryIds": [entry["entryId"]], "assigneeUserId": ""}
        ).status_code
        == 403
    )
    # 非项目成员不能被指定为执行人
    assert (
        api.post(
            url, headers=owner, json={"entryIds": [entry["entryId"]], "assigneeUserId": "nobody"}
        ).status_code
        == 400
    )
    # 空串表示取消分配
    cleared = api.post(
        url, headers=owner, json={"entryIds": [entry["entryId"]], "assigneeUserId": ""}
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["data"]["items"][0]["assigneeUserId"] == ""


def seed_retest_source(db) -> None:
    db.add(
        Sprint(
            sprint_id="s-retest",
            project_id="p",
            name="迭代",
            start_time=datetime(2026, 9, 1, tzinfo=UTC),
            end_time=datetime(2026, 10, 1, tzinfo=UTC),
        )
    )
    db.add(
        test_order_models.TestOrder(
            order_id="o-source",
            project_id="p",
            sprint_id="s-retest",
            name="第一轮",
            tested_version="rc1",
        )
    )
    db.add_all(
        [
            test_order_entry_models.TestOrderEntry(
                entry_id="e-passed",
                order_id="o-source",
                case_id="c-passed",
                order_no=1,
                status="passed",
            ),
            test_order_entry_models.TestOrderEntry(
                entry_id="e-failed",
                order_id="o-source",
                case_id="c-failed",
                order_no=2,
                status="failed",
            ),
            test_order_entry_models.TestOrderEntry(
                entry_id="e-pending",
                order_id="o-source",
                case_id="c-pending",
                order_no=3,
                status="pending",
            ),
        ]
    )
    db.commit()


@pytest.mark.asyncio
async def test_retest_copies_only_non_passed_entries_as_unexecuted(db):
    seed_retest_source(db)
    session = AsyncSessionAdapter(db)
    entries_repository = test_order_entry_repositories.TestOrderEntryRepository(session)
    orders = test_order_services.TestOrderService(
        test_order_repositories.TestOrderRepository(session), entries_repository
    )
    entry_service = test_order_entry_services.TestOrderEntryService(entries_repository, orders)

    created = await orders.create(
        "u",
        "s-retest",
        test_order_schemas.TestOrderRequest(name="第二轮", source_order_id="o-source"),
    )
    assert created["entriesTotal"] == 2
    assert created["status"] == "pending"

    listing = await entry_service.list("u", created["orderId"])
    assert {item["caseId"] for item in listing["items"]} == {"c-failed", "c-pending"}
    assert {item["status"] for item in listing["items"]} == {"pending"}
    assert [item["orderNo"] for item in listing["items"]] == [1, 2]


@pytest.mark.asyncio
async def test_retest_rejects_a_source_order_from_another_project(db):
    seed_retest_source(db)
    db.add(Project(project_id="other-project", user_id="u", name="别的项目"))
    db.add(
        test_order_models.TestOrder(
            order_id="o-other",
            project_id="other-project",
            sprint_id="s-retest",
            name="别的项目",
            tested_version="",
        )
    )
    db.commit()
    session = AsyncSessionAdapter(db)
    orders = test_order_services.TestOrderService(
        test_order_repositories.TestOrderRepository(session),
        test_order_entry_repositories.TestOrderEntryRepository(session),
    )

    with pytest.raises(AppError) as error:
        await orders.create(
            "u",
            "s-retest",
            test_order_schemas.TestOrderRequest(name="跨项目", source_order_id="o-other"),
        )
    assert error.value.code == 3606


def test_judging_a_case_sets_its_status_and_records_results(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid)
    requirement_id = make_requirement(api, owner, sprint_id)
    case_id = seed_case(
        api,
        owner,
        requirement_id,
        content={
            "preconditions": ["已进入页面"],
            "steps": [
                {"action": "第一步", "expected": "预期一"},
                {"action": "第二步", "expected": "预期二"},
            ],
        },
    )
    order = make_order(api, owner, sprint_id)
    api.post(
        f"/v1/test-orders/{order['orderId']}/cases", headers=owner, json={"caseIds": [case_id]}
    )
    entry = entries_of(api, owner, order["orderId"])["items"][0]
    url = f"/v1/test-orders/{order['orderId']}/entries/{entry['entryId']}"

    # 执行针对整条用例：一次判定带上实际结果、失败原因与缺陷号
    failed = api.patch(
        url,
        headers=owner,
        json={
            "status": "failed",
            "actualResults": "第二步报错",
            "failureReason": "阈值不对",
            "zentaoBugId": "BUG-20418",
        },
    )
    assert failed.status_code == 200, failed.text
    data = failed.json()["data"]
    assert data["status"] == "failed"
    assert data["actualResults"] == "第二步报错"
    assert data["failureReason"] == "阈值不对"
    assert data["zentaoBugId"] == "BUG-20418"
    assert data["executorUserId"]
    assert data["executedAt"]
    # 步骤只是只读说明，不作为结果返回
    assert "stepResults" not in data

    # 改判为通过
    passed = api.patch(url, headers=owner, json={"status": "passed"})
    assert passed.json()["data"]["status"] == "passed"

    # 阻塞带上阻塞原因
    blocked = api.patch(
        url, headers=owner, json={"status": "blocked", "blockReason": "依赖上游缺陷"}
    )
    assert blocked.json()["data"]["status"] == "blocked"
    assert blocked.json()["data"]["blockReason"] == "依赖上游缺陷"

    # 不接受未知状态
    assert api.patch(url, headers=owner, json={"status": "nope"}).status_code == 400

    # 测试单进度随判定变化（阻塞也计入已执行）
    refreshed = api.get(f"/v1/test-orders/{order['orderId']}", headers=owner).json()["data"]
    assert refreshed["entriesTotal"] == 1
    assert refreshed["entriesExecuted"] == 1
    assert refreshed["entriesBlocked"] == 1
    assert refreshed["status"] == "completed"

    # 重新打开工作台时，条目带着快照与判定结果
    entry_after = entries_of(api, owner, order["orderId"])["items"][0]
    assert entry_after["snapshot"]["steps"][1]["action"] == "第二步"
    assert entry_after["status"] == "blocked"


def test_assigned_entries_can_only_be_judged_by_the_assignee(api):
    _, owner = account(api, "owner")
    member_user, member = account(api, "member")
    other_user, other = account(api, "other")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid)
    requirement_id = make_requirement(api, owner, sprint_id)
    case_id = seed_case(api, owner, requirement_id)
    order = make_order(api, owner, sprint_id)
    api.post(
        f"/v1/test-orders/{order['orderId']}/cases", headers=owner, json={"caseIds": [case_id]}
    )
    entry = entries_of(api, owner, order["orderId"])["items"][0]
    url = f"/v1/test-orders/{order['orderId']}/entries/{entry['entryId']}"
    for name in ("member", "other"):
        assert (
            api.post(
                f"/v1/projects/{pid}/members", headers=owner, json={"name": name, "role": "member"}
            ).status_code
            == 200
        )

    api.post(
        f"/v1/test-orders/{order['orderId']}/entries/assign",
        headers=owner,
        json={"entryIds": [entry["entryId"]], "assigneeUserId": member_user["userId"]},
    )
    # 被分配的人可以判定
    assert (
        api.patch(
            url, headers=member, json={"status": "blocked", "blockReason": "环境不可用"}
        ).status_code
        == 200
    )
    # 其他人不行
    denied = api.patch(url, headers=other, json={"status": "skipped"})
    assert denied.status_code == 403, denied.text
    assert denied.json()["code"] == 3608
    # 项目所有者不受限
    assert api.patch(url, headers=owner, json={"status": "skipped"}).status_code == 200
    # 未分配的条目谁都能跑
    other_case = seed_case(api, owner, requirement_id, title="未分配用例")
    api.post(
        f"/v1/test-orders/{order['orderId']}/cases", headers=owner, json={"caseIds": [other_case]}
    )
    free_entry = [
        item
        for item in entries_of(api, owner, order["orderId"])["items"]
        if item["caseId"] == other_case
    ][0]
    free_url = f"/v1/test-orders/{order['orderId']}/entries/{free_entry['entryId']}"
    assert api.patch(free_url, headers=other, json={"status": "skipped"}).status_code == 200


def test_batch_mark_passed_only_affects_unexecuted_entries(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid)
    requirement_id = make_requirement(api, owner, sprint_id)
    case_a = seed_case(
        api,
        owner,
        requirement_id,
        title="A",
        content={"preconditions": [], "steps": [{"action": "第一步", "expected": "预期"}]},
    )
    case_b = seed_case(api, owner, requirement_id, title="B")
    order = make_order(api, owner, sprint_id)
    api.post(
        f"/v1/test-orders/{order['orderId']}/cases",
        headers=owner,
        json={"caseIds": [case_a, case_b]},
    )
    entries = entries_of(api, owner, order["orderId"])["items"]
    first = f"/v1/test-orders/{order['orderId']}/entries/{entries[0]['entryId']}"
    failed = api.patch(first, headers=owner, json={"status": "failed", "failureReason": "不行"})
    assert failed.status_code == 200, failed.text
    assert failed.json()["data"]["status"] == "failed"
    assert [item["status"] for item in entries_of(api, owner, order["orderId"])["items"]] == [
        "failed",
        "pending",
    ]

    url = f"/v1/test-orders/{order['orderId']}/entries/batch-mark-passed"
    marked = api.post(url, headers=owner, json={"entryIds": [item["entryId"] for item in entries]})
    assert marked.status_code == 200, marked.text
    # 已失败的那条不是「未执行」，被跳过
    assert marked.json()["data"] == {"markedCount": 1, "skippedCount": 1}

    after = entries_of(api, owner, order["orderId"])["items"]
    assert {item["status"] for item in after} == {"failed", "passed"}
    passed = [item for item in after if item["status"] == "passed"][0]
    assert passed["executorUserId"]


@pytest.mark.asyncio
async def test_function_metrics_come_from_local_test_orders(db):
    seed_retest_source(db)
    db.add(
        Sprint(
            sprint_id="s-local",
            project_id="p",
            name="本地迭代",
            start_time=datetime(2026, 9, 1, tzinfo=UTC),
            end_time=datetime(2026, 10, 1, tzinfo=UTC),
        )
    )
    db.add(
        test_order_models.TestOrder(
            order_id="o-local",
            project_id="p",
            sprint_id="s-local",
            name="本地单",
            tested_version="",
        )
    )
    db.add_all(
        [
            test_order_entry_models.TestOrderEntry(
                entry_id="l1", order_id="o-local", case_id="c1", order_no=1, status="passed"
            ),
            test_order_entry_models.TestOrderEntry(
                entry_id="l2", order_id="o-local", case_id="c2", order_no=2, status="failed"
            ),
            test_order_entry_models.TestOrderEntry(
                entry_id="l3", order_id="o-local", case_id="c3", order_no=3, status="blocked"
            ),
            test_order_entry_models.TestOrderEntry(
                entry_id="l4", order_id="o-local", case_id="c4", order_no=4, status="pending"
            ),
        ]
    )
    db.commit()
    session = AsyncSessionAdapter(db)
    service = SprintDailyMetricsService(SprintDailyMetricsRepository(session))
    metrics = await service.load_function_metrics_from_local_runs("s-local")
    assert (metrics.total, metrics.executed, metrics.pending) == (4, 3, 1)
    assert (metrics.success, metrics.failed) == (1, 2)
    # 另一个迭代没有测试单 → 全零，界面据此显示空态
    empty = await service.load_function_metrics_from_local_runs("s-unknown")
    assert (empty.total, empty.executed, empty.pending) == (0, 0, 0)
