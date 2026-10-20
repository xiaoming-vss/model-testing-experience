"""Current UI ownership drives permissions and live metrics; snapshots stay stored."""

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db
from support.ui_run_scope import (
    seed as seed,
)

from testing_agent.core.errors import ErrForbidden
from testing_agent.models.requirement import Requirement
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.repositories.sprint_daily_metrics import SprintDailyMetricsRepository
from testing_agent.repositories.ui_test_case_run import UiTestCaseRunRepository
from testing_agent.schemas.ui_run import DebugRunUiCaseRequest, RunUiSuiteRequest
from testing_agent.services.ui_test_case_run import UiTestCaseRunService


@pytest.mark.asyncio
async def test_scope_move_updates_permissions_and_live_metrics_not_saved_daily_counts(db):
    seed(db)
    service = UiTestCaseRunService(UiTestCaseRunRepository(AsyncSessionAdapter(db)))
    single = await service.debug_run_case("u1", "case", DebugRunUiCaseRequest())
    suite = await service.run_suite("u1", "suite", RunUiSuiteRequest())
    assert single["projectId"] == suite["projectId"] == "p1"
    assert single["requirementId"] == "req" and suite["sprintId"] == "s1"
    metrics = SprintDailyMetricsRepository(AsyncSessionAdapter(db))
    assert len(await metrics.list_latest_ui_suite_runs("s1")) == 1
    req = db.scalar(select(Requirement))
    req.sprint_id = "s2"
    db.commit()
    assert await metrics.list_latest_ui_suite_runs("s1") == []
    assert len(await metrics.list_latest_ui_suite_runs("s2")) == 1
    with pytest.raises(type(ErrForbidden)):
        await service.get_case_run("u1", single["runId"])
    with pytest.raises(type(ErrForbidden)):
        await service.suite_report("u1", suite["suiteRunId"])
    moved = await service.get_suite_run("u2", suite["suiteRunId"])
    assert moved["sprintId"] == "s2" and moved["projectId"] == "p2"
    moved_case = await service.get_case_run("u2", single["runId"])
    assert moved_case["projectId"] == "p2"
    history = await metrics.get("s1", "2026-09-10")
    assert history.ui_case_total == 7 and history.ui_case_success == 6
    from testing_agent.core.errors import ErrNotFound
    from testing_agent.services.resource_deletion import delete_resource

    adapter = AsyncSessionAdapter(db)
    for case in list(db.scalars(select(UiTestCase))):
        await delete_resource(adapter, case)
    await delete_resource(adapter, db.scalar(select(UiTestSuite)))
    db.commit()
    assert await metrics.list_latest_ui_suite_runs("s2") == []
    with pytest.raises(type(ErrNotFound)):
        await service.suite_report("u2", suite["suiteRunId"])
