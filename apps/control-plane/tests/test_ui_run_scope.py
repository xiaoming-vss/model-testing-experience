"""Current UI ownership drives permissions and live metrics; snapshots stay stored."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from test_ai_execution_storage import AsyncSessionAdapter
from test_ai_execution_storage import db as db
from test_worker_queue_storage import row

from testing_agent.core.errors import ErrForbidden
from testing_agent.db.base import Base
from testing_agent.models.project import Project
from testing_agent.models.project_member import ProjectMember
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.sprint_daily_metrics import SprintDailyMetrics
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_case_run import UiTestCaseRun
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.models.ui_test_suite_run import UiTestSuiteRun, UiTestSuiteRunItem
from testing_agent.models.user import User
from testing_agent.repositories.sprint_daily_metrics import SprintDailyMetricsRepository
from testing_agent.repositories.ui_test_case_run import UiTestCaseRunRepository
from testing_agent.schemas.ui_run import DebugRunUiCaseRequest, RunUiSuiteRequest
from testing_agent.services.ui_test_case_run import UiTestCaseRunService


def seed(db):
    models = (
        ProjectMember,
        Project,
        Sprint,
        Requirement,
        UiTestSuite,
        UiTestCase,
        UiTestCaseRun,
        UiTestSuiteRun,
        UiTestSuiteRunItem,
        SprintDailyMetrics,
    )
    Base.metadata.create_all(db.get_bind(), tables=[m.__table__ for m in models])
    now = datetime.now(UTC)
    for item in [
        row(User, user_id="u1", nickname="u1"),
        row(User, user_id="u2", nickname="u2"),
        row(Project, project_id="p1", user_id="u1"),
        row(Project, project_id="p2", user_id="u2"),
        row(
            Sprint,
            sprint_id="s1",
            project_id="p1",
            start_time=now,
            end_time=now + timedelta(days=1),
        ),
        row(
            Sprint,
            sprint_id="s2",
            project_id="p2",
            start_time=now,
            end_time=now + timedelta(days=1),
        ),
        row(Requirement, requirement_id="req", sprint_id="s1"),
        row(UiTestSuite, suite_id="suite", requirement_id="req"),
        row(UiTestCase, case_id="case", suite_id="suite", steps_json=[]),
        row(
            SprintDailyMetrics,
            metric_id="history",
            sprint_id="s1",
            project_id="p1",
            snapshot_date=date(2026, 9, 10),
            ui_case_total=7,
            ui_case_success=6,
        ),
    ]:
        db.add(item)
        db.flush()
    db.commit()


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
    from testing_agent.repositories.deletion import delete_resource

    adapter = AsyncSessionAdapter(db)
    for case in list(db.scalars(select(UiTestCase))):
        await delete_resource(adapter, case)
    await delete_resource(adapter, db.scalar(select(UiTestSuite)))
    db.commit()
    assert await metrics.list_latest_ui_suite_runs("s2") == []
    with pytest.raises(type(ErrNotFound)):
        await service.suite_report("u2", suite["suiteRunId"])
