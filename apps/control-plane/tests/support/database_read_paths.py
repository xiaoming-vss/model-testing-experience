"""Shared preparation for database read paths tests; no collected cases."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import mysql

from support.ai_execution import db  # noqa: F401
from testing_agent.models.ai_generate_execution import (
    AiGenerateRunImport as Import,
)
from testing_agent.models.ai_generate_execution import (
    AiGenerateRunStage as Stage,
)
from testing_agent.models.ai_generate_execution import (
    AiGenerateStageAttempt as Attempt,
)
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generate_task import AiGenerateTaskRun as Run
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_case_run import UiTestCaseRun
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.models.ui_test_suite_run import UiTestSuiteRun

NOW = datetime(2026, 10, 4, tzinfo=UTC)


class AsyncAdapter:
    """Exercise real SQL in the existing SQLite fixture through the async interface."""

    def __init__(self, sync):
        self.sync = sync

    async def execute(self, statement):
        return self.sync.execute(statement)

    async def scalar(self, statement):
        return self.sync.scalar(statement)

    async def scalars(self, statement):
        return self.sync.scalars(statement)

    async def rollback(self):
        self.sync.rollback()

    async def run_sync(self, operation):
        return operation(self.sync)


@pytest.fixture
def database(db):  # noqa: F811
    db.add(
        Sprint(
            sprint_id="s",
            project_id="p",
            name="s",
            start_time=NOW,
            end_time=NOW + timedelta(days=1),
        )
    )
    db.flush()
    db.add_all(
        [
            Requirement(requirement_id="req", sprint_id="s", name="req"),
            Requirement(requirement_id="other", sprint_id="s", name="other"),
        ]
    )
    db.flush()
    db.add(
        AiGenerateTask(
            task_id="task",
            task_type="functional_case_generate",
            name="task",
            project_id="p",
            sprint_id="s",
            requirement_id="req",
            creator_user_id="u",
            source_type="text",
            source_content="input",
        )
    )
    db.commit()
    statements = []

    def record(connection, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(db.bind, "before_cursor_execute", record)
    yield db, AsyncAdapter(db), statements
    event.remove(db.bind, "before_cursor_execute", record)


def seed_history(session, size=25):
    for i in range(size):
        run_id = f"run-{i:02d}"
        session.add(
            Run(
                run_id=run_id,
                task_id="task",
                trigger_user_id="u",
                status="success",
                current_stage="completed",
                snapshot_json={"source": "X" * 200_000},
                created_at=NOW,
                started_at=NOW,
                finished_at=NOW + timedelta(seconds=2),
            )
        )
        session.flush()
        session.add(
            Stage(
                id=f"stage-{i}",
                run_id=run_id,
                stage="detailed_cases",
                stage_order=2,
                execution_status="success",
                review_status="approved" if i == 0 else "pending",
                current_artifact_attempt_id=f"artifact-{i}",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.flush()
        session.add(
            Attempt(
                id=f"artifact-{i}",
                stage_id=f"stage-{i}",
                attempt_no=1,
                operation="generate",
                status="success",
                created_at=NOW,
                input_snapshot_json={"source": "X" * 200_000},
                output_content="cases: " + "Y" * 200_000,
                output_context_json={"secret": "Z" * 200_000},
            )
        )
    session.flush()
    session.add(
        Import(
            id="import",
            run_id="run-00",
            imported_at=NOW,
            imported_targets_json=[],
        )
    )
    session.commit()
    session.expunge_all()


class CapturingSession:
    async def rollback(self):
        self.sync.rollback()

    async def run_sync(self, operation):
        return operation(self)

    def __init__(self):
        self.statements = []

    async def scalar(self, statement):
        self.statements.append(str(statement.compile(dialect=mysql.dialect())))
        return None


def seed_cases(session, size):
    session.add_all(
        [
            ApiCollection(collection_id="ac", requirement_id="req", name="api"),
            FunctionTestSuite(suite_id="fc", requirement_id="req", name="function"),
            UiTestSuite(suite_id="uc", requirement_id="req", name="ui"),
            ApiCollection(collection_id="foreign", requirement_id="other", name="foreign"),
        ]
    )
    session.flush()
    for i in range(size):
        session.add_all(
            [
                ApiCase(
                    case_id=f"api-{i}",
                    collection_id="ac",
                    name=f"api-{i}",
                    method="GET",
                    url_template="/",
                ),
                FunctionTestCase(case_id=f"function-{i}", suite_id="fc", title=f"function-{i}"),
                UiTestCase(case_id=f"ui-{i}", suite_id="uc", name=f"ui-{i}", steps_json=[]),
            ]
        )
        session.flush()
        for j, status in enumerate(["failed", "success"]):
            session.add_all(
                [
                    ApiCaseRun(
                        run_id=f"api-{i}-{j}",
                        case_id=f"api-{i}",
                        collection_id="ac",
                        environment_id="e",
                        trigger_user_id="u",
                        status=status,
                        created_at=NOW,
                        finished_at=NOW,
                        private_payload="X" * 100_000,
                    ),
                    UiTestCaseRun(
                        run_id=f"ui-{i}-{j}",
                        case_id=f"ui-{i}",
                        suite_id="uc",
                        trigger_user_id="u",
                        status=status,
                        created_at=NOW,
                        finished_at=NOW,
                        snapshot_json={"large": "X" * 100_000},
                    ),
                ]
            )
    session.add(
        ApiCase(
            case_id="foreign-api",
            collection_id="foreign",
            name="foreign",
            method="GET",
            url_template="/",
        )
    )
    session.add_all(
        [
            UiTestSuiteRun(
                suite_run_id="old",
                suite_id="uc",
                trigger_user_id="u",
                created_at=NOW,
                total_count=7,
                success_count=0,
                failed_count=7,
            ),
            UiTestSuiteRun(
                suite_run_id="new",
                suite_id="uc",
                trigger_user_id="u",
                created_at=NOW,
                total_count=3,
                success_count=2,
                failed_count=1,
                snapshot_json={"large": "X" * 100_000},
            ),
        ]
    )
    session.commit()
    session.expunge_all()
