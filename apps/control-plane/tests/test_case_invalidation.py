"""用例失效标记：批量状态、列表筛选与新执行/分析边界。"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from support.ai_execution import AsyncSessionAdapter  # noqa: F401
from support.ai_execution import db as db
from support.function_case_library import make_case, make_requirement, make_sprint, make_suite
from support.project_api import account, project
from support.project_api import api as api  # noqa: F401

from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.sprint_daily_metrics import SprintDailyMetricsRepository
from testing_agent.services.api_import_entities import apply_api_case
from testing_agent.services.function_generate_import import apply_generated_case
from testing_agent.services.ui_generate_import import (
    apply_generated_case as apply_ui_generated_case,
)

PERF_YAML = """
specVersion: "1.0"
case:
  name: ping
  steps:
    - name: ping
      method: GET
      path: /ping
      checks:
        - type: status
          op: eq
          value: 200
  load:
    model: vus
    vus: 1
    duration: "1s"
  acceptance:
    source: user_confirmed
    confirmed: true
    criteria:
      http_req_failed: ["rate<0.01"]
"""

UI_STEPS = [
    {
        "orderNo": 1,
        "stepName": "打开页面",
        "keyword": "open",
        "operationValue": "http://127.0.0.1:5173/",
        "continueOnFailure": False,
        "enabled": True,
    }
]


def _project_with_requirement(api, owner):
    pid = project(api, owner)
    sid = make_sprint(api, owner, pid)
    rid = make_requirement(api, owner, sid)
    return pid, sid, rid


def _function_case(api, owner, rid, title):
    suite = make_suite(api, owner, rid, name=f"{title}集")
    return make_case(api, owner, suite, title=title)


def _api_collection(api, owner, rid):
    response = api.post(
        f"/v1/requirements/{rid}/api-collections", headers=owner, json={"name": "集合"}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["collectionId"]


def _api_case(api, owner, collection_id, name):
    response = api.post(
        f"/v1/api-collections/{collection_id}/cases",
        headers=owner,
        json={"name": name, "method": "GET", "urlTemplate": f"/{name}"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["caseId"]


def _environment(api, owner, project_id, kind):
    response = api.post(
        f"/v1/projects/{project_id}/api-environments",
        headers=owner,
        json={"name": f"{kind}-env", "kind": kind, "baseUrl": "http://127.0.0.1:18080"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["environmentId"]


def _ui_suite(api, owner, rid):
    response = api.post(
        f"/v1/requirements/{rid}/ui-test-suites", headers=owner, json={"name": "UI 套件"}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["suiteId"]


def _ui_case(api, owner, suite_id, name, order_no):
    response = api.post(
        f"/v1/ui-test-suites/{suite_id}/cases",
        headers=owner,
        json={"name": name, "orderNo": order_no, "stepsJson": UI_STEPS},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["caseId"]


def _perf_suite(api, owner, project_id):
    response = api.post(
        f"/v1/projects/{project_id}/perf-suites", headers=owner, json={"name": "性能套件"}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["suiteId"]


def _perf_case(api, owner, project_id, suite_id, name):
    response = api.post(
        f"/v1/projects/{project_id}/perf-cases",
        headers=owner,
        json={"name": name, "yaml": PERF_YAML, "suiteId": suite_id},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["caseId"]


def _invalidate(api, owner, project_id, kind, case_ids, invalidated=True):
    response = api.post(
        f"/v1/projects/{project_id}/{kind}/batch-invalidation",
        headers=owner,
        json={"caseIds": case_ids, "invalidated": invalidated},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _items(api, owner, path):
    response = api.get(path, headers=owner)
    assert response.status_code == 200, response.text
    return response.json()["data"]["items"]


def test_function_case_batch_invalidation_filters_and_is_idempotent(api):
    _, owner = account(api, "owner")
    pid, _sid, rid = _project_with_requirement(api, owner)
    first = _function_case(api, owner, rid, "登录成功")
    second = _function_case(api, owner, rid, "登录失败")

    result = _invalidate(api, owner, pid, "function-test-cases", [first, second])
    assert result["updatedCount"] == 2

    all_items = _items(api, owner, f"/v1/projects/{pid}/function-test-cases")
    by_id = {item["caseId"]: item for item in all_items}
    assert by_id[first]["invalidatedAt"] and by_id[second]["invalidatedAt"]
    first_invalidated_at = by_id[first]["invalidatedAt"]

    assert len(_items(api, owner, f"/v1/projects/{pid}/function-test-cases?invalidated=true")) == 2
    assert len(_items(api, owner, f"/v1/projects/{pid}/function-test-cases?invalidated=false")) == 0

    repeated = _invalidate(api, owner, pid, "function-test-cases", [first, second])
    assert repeated["updatedCount"] == 0
    unchanged = _items(api, owner, f"/v1/projects/{pid}/function-test-cases?invalidated=true")
    unchanged_by_id = {item["caseId"]: item["invalidatedAt"] for item in unchanged}
    assert unchanged_by_id[first] == first_invalidated_at

    restored = _invalidate(
        api, owner, pid, "function-test-cases", [first, second], invalidated=False
    )
    assert restored["updatedCount"] == 2
    assert len(_items(api, owner, f"/v1/projects/{pid}/function-test-cases?invalidated=false")) == 2

    missing = api.post(
        f"/v1/projects/{pid}/function-test-cases/batch-invalidation",
        headers=owner,
        json={"caseIds": ["missing"], "invalidated": True},
    )
    assert missing.status_code == 404


def test_api_case_invalidation_filters_and_exits_new_runs(api):
    _, owner = account(api, "owner")
    pid, _sid, rid = _project_with_requirement(api, owner)
    collection_id = _api_collection(api, owner, rid)
    invalid_case = _api_case(api, owner, collection_id, "first")
    valid_case = _api_case(api, owner, collection_id, "second")
    environment_id = _environment(api, owner, pid, "api")

    _invalidate(api, owner, pid, "api-cases", [invalid_case])

    all_cases = _items(api, owner, f"/v1/api-collections/{collection_id}/cases")
    by_id = {item["caseId"]: item for item in all_cases}
    assert by_id[invalid_case]["invalidatedAt"]
    assert by_id[valid_case]["invalidatedAt"] is None
    invalid_cases = _items(
        api, owner, f"/v1/api-collections/{collection_id}/cases?invalidated=true"
    )
    valid_cases = _items(api, owner, f"/v1/api-collections/{collection_id}/cases?invalidated=false")
    assert len(invalid_cases) == 1
    assert len(valid_cases) == 1

    rejected = api.post(
        f"/v1/api-cases/{invalid_case}/run",
        headers=owner,
        json={"environmentId": environment_id},
    )
    assert rejected.status_code == 409
    assert rejected.json()["code"] == 2405

    collection_run = api.post(
        f"/v1/api-collections/{collection_id}/run",
        headers=owner,
        json={"environmentId": environment_id},
    )
    assert collection_run.status_code == 200, collection_run.text
    assert collection_run.json()["data"]["totalCount"] == 1

    _invalidate(api, owner, pid, "api-cases", [valid_case])
    all_invalid = api.post(
        f"/v1/api-collections/{collection_id}/run",
        headers=owner,
        json={"environmentId": environment_id},
    )
    assert all_invalid.status_code == 400
    assert "没有有效用例" in all_invalid.json()["message"]


def test_ui_case_invalidation_filters_and_exits_new_runs(api):
    _, owner = account(api, "owner")
    pid, _sid, rid = _project_with_requirement(api, owner)
    suite_id = _ui_suite(api, owner, rid)
    invalid_case = _ui_case(api, owner, suite_id, "登录失效", 1)
    valid_case = _ui_case(api, owner, suite_id, "登录成功", 2)
    environment_id = _environment(api, owner, pid, "ui")

    _invalidate(api, owner, pid, "ui-test-cases", [invalid_case])

    all_cases = _items(api, owner, f"/v1/ui-test-suites/{suite_id}/cases")
    by_id = {item["caseId"]: item for item in all_cases}
    assert by_id[invalid_case]["invalidatedAt"]
    assert by_id[valid_case]["invalidatedAt"] is None
    assert len(_items(api, owner, f"/v1/ui-test-suites/{suite_id}/cases?invalidated=true")) == 1
    assert len(_items(api, owner, f"/v1/ui-test-suites/{suite_id}/cases?invalidated=false")) == 1

    rejected = api.post(
        f"/v1/ui-test-cases/{invalid_case}/debug-run",
        headers=owner,
        json={"environmentId": environment_id},
    )
    assert rejected.status_code == 409
    assert rejected.json()["code"] == 2904

    suite_run = api.post(
        f"/v1/ui-test-suites/{suite_id}/run",
        headers=owner,
        json={"environmentId": environment_id},
    )
    assert suite_run.status_code == 200, suite_run.text
    assert suite_run.json()["data"]["totalCount"] == 1

    _invalidate(api, owner, pid, "ui-test-cases", [valid_case])
    all_invalid = api.post(
        f"/v1/ui-test-suites/{suite_id}/run",
        headers=owner,
        json={"environmentId": environment_id},
    )
    assert all_invalid.status_code == 400
    assert "没有有效用例" in all_invalid.json()["message"]


def test_perf_case_invalidation_filters_and_exits_new_runs(api):
    _, owner = account(api, "owner")
    pid = project(api, owner)
    suite_id = _perf_suite(api, owner, pid)
    case_id = _perf_case(api, owner, pid, suite_id, "ping")

    _invalidate(api, owner, pid, "perf-cases", [case_id])

    all_cases = _items(api, owner, f"/v1/projects/{pid}/perf-cases")
    by_id = {item["caseId"]: item for item in all_cases}
    assert by_id[case_id]["invalidatedAt"]
    assert len(_items(api, owner, f"/v1/projects/{pid}/perf-cases?invalidated=true")) == 1
    assert len(_items(api, owner, f"/v1/projects/{pid}/perf-cases?invalidated=false")) == 0

    rejected = api.post(
        f"/v1/perf-cases/{case_id}/runs",
        headers=owner,
        json={"environmentId": "environment", "monitoringConnectionId": "connection"},
    )
    assert rejected.status_code == 409
    assert rejected.json()["code"] == 3903

    suite_run = api.post(
        f"/v1/perf-suites/{suite_id}/runs",
        headers=owner,
        json={"environmentId": "environment", "monitoringConnectionId": "connection"},
    )
    assert suite_run.status_code == 400


def test_test_order_rejects_new_invalid_cases_but_keeps_existing_entries(api):
    _, owner = account(api, "owner")
    pid, sid, rid = _project_with_requirement(api, owner)
    existing_case = _function_case(api, owner, rid, "已在测试单")
    new_case = _function_case(api, owner, rid, "后来新增")

    order = api.post(
        f"/v1/sprints/{sid}/test-orders",
        headers=owner,
        json={"name": "测试单", "testedVersion": "V1"},
    )
    assert order.status_code == 200, order.text
    order_id = order.json()["data"]["orderId"]
    added = api.post(
        f"/v1/test-orders/{order_id}/cases", headers=owner, json={"caseIds": [existing_case]}
    )
    assert added.status_code == 200, added.text

    _invalidate(api, owner, pid, "function-test-cases", [existing_case, new_case])

    rejected = api.post(
        f"/v1/test-orders/{order_id}/cases", headers=owner, json={"caseIds": [new_case]}
    )
    assert rejected.status_code == 409
    assert rejected.json()["code"] == 3304
    assert rejected.json()["data"]["invalidCaseIds"] == [new_case]

    entries = _items(api, owner, f"/v1/test-orders/{order_id}/entries")
    entry = next(item for item in entries if item["caseId"] == existing_case)
    updated = api.patch(
        f"/v1/test-orders/{order_id}/entries/{entry['entryId']}",
        headers=owner,
        json={"status": "passed"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["status"] == "passed"


async def test_ai_inputs_and_api_metrics_skip_invalid_cases(db):  # noqa: F811
    now = datetime.now(UTC)
    db.add(
        Sprint(
            sprint_id="s",
            project_id="p",
            name="sprint",
            start_time=datetime(2026, 1, 1, tzinfo=UTC),
            end_time=datetime(2026, 2, 1, tzinfo=UTC),
        )
    )
    db.flush()
    db.add(Requirement(requirement_id="r", sprint_id="s", name="requirement"))
    db.flush()
    db.add(FunctionTestSuite(suite_id="suite", requirement_id="r", name="suite"))
    db.add(
        ApiCollection(
            collection_id="collection", project_id="p", requirement_id="r", name="collection"
        )
    )
    db.flush()
    db.add_all(
        [
            FunctionTestCase(
                case_id="valid",
                suite_id="suite",
                title="valid",
                content={"preconditions": [], "steps": []},
            ),
            FunctionTestCase(
                case_id="invalid",
                suite_id="suite",
                title="invalid",
                content={"preconditions": [], "steps": []},
                invalidated_at=now,
            ),
            ApiCase(
                case_id="api-valid",
                collection_id="collection",
                name="api-valid",
                method="GET",
                url_template="/valid",
            ),
            ApiCase(
                case_id="api-invalid",
                collection_id="collection",
                name="api-invalid",
                method="GET",
                url_template="/invalid",
                invalidated_at=now,
            ),
        ]
    )
    db.commit()
    adapter = AsyncSessionAdapter(db)

    pairs = await AiGenerateTaskRepository(adapter).list_requirement_case_pairs("r", "function")
    assert [case.case_id for case, _suite in pairs] == ["valid"]
    source_cases = await AiGenerateTaskRepository(adapter).list_ui_source_cases("r")
    assert [item["caseId"] for item in source_cases] == ["valid"]
    api_case_ids = await SprintDailyMetricsRepository(adapter).list_api_case_ids_by_sprint("s")
    assert api_case_ids == ["api-valid"]


def test_generated_import_overwrite_restores_invalidated_cases():
    now = datetime.now(UTC)
    function_case = FunctionTestCase(
        case_id="function",
        suite_id="suite",
        title="old",
        content={"preconditions": [], "steps": []},
        invalidated_at=now,
    )
    apply_generated_case(
        function_case,
        {
            "module": "module",
            "title": "new",
            "preconditions": "",
            "steps": "",
            "expected_results": "",
            "priority": "P0",
            "case_type": "功能测试",
        },
    )
    assert function_case.invalidated_at is None

    api_case = SimpleNamespace(
        name="old",
        description="",
        enabled=True,
        order_no=1,
        method="GET",
        url_template="/old",
        headers_json={},
        query_json={},
        body_type="none",
        body_json=None,
        body_text="",
        timeout_ms=1000,
        continue_on_failure=False,
        invalidated_at=now,
    )
    apply_api_case(
        api_case,
        {
            "name": "new",
            "description": "",
            "enabled": True,
            "orderNo": 1,
            "method": "GET",
            "urlTemplate": "/new",
            "headers": {},
            "query": {},
            "bodyType": "none",
            "bodyJson": None,
            "bodyText": "",
            "timeoutMs": 1000,
            "continueOnFailure": False,
        },
    )
    assert api_case.invalidated_at is None

    ui_case = SimpleNamespace(
        name="old", enabled=True, order_no=1, steps_json=[], invalidated_at=now
    )
    apply_ui_generated_case(
        ui_case,
        {"name": "new", "enabled": True, "orderNo": 1, "stepsJson": []},
    )
    assert ui_case.invalidated_at is None
