"""Shared preparation for test order api tests; no collected cases."""

from datetime import UTC, datetime

from support.ai_execution import db as db
from support.function_case_library import make_case, make_suite
from support.project_api import api as api
from testing_agent.models import test_order as test_order_models
from testing_agent.models import test_order_entry as test_order_entry_models
from testing_agent.models.sprint import Sprint


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
