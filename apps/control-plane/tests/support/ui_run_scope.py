"""Shared preparation for ui run scope tests; no collected cases."""

from datetime import UTC, date, datetime, timedelta

from support.ai_execution import db as db
from support.worker_queue_storage import row
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
