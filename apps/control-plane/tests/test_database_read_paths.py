"""SQL/result contracts for bounded histories and batched snapshot reads."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, select
from sqlalchemy.dialects import mysql
from support.ai_execution import db  # noqa: F401

from testing_agent.core.errors import AppError
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
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.ai_run_history import history_page
from testing_agent.repositories.resource_binding import ResourceBindingRepository
from testing_agent.repositories.sprint_daily_metrics import SprintDailyMetricsRepository
from testing_agent.services.ai_generate_task import AiGenerateTaskService
from testing_agent.services.code_risk_analysis import CodeRiskAnalysisService

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


async def test_history_is_bounded_and_omits_large_inputs_outputs(database):
    sync, session, sql = database
    seed_history(sync)
    sql.clear()
    first = await history_page(session, [Run.task_id == "task"], 1, 20)
    second = await history_page(session, [Run.task_id == "task"], 2, 20)
    assert first["total"] == second["total"] == 25
    assert len(first["items"]) == 20 and len(second["items"]) == 5
    assert first["items"][0]["runId"] == "run-24"
    assert second["latestRun"]["runId"] == "run-24"
    assert not {item["runId"] for item in first["items"]} & {
        item["runId"] for item in second["items"]
    }
    assert first["statusCounts"] == {"success": 25}
    assert first["reviewPendingCount"] == second["reviewPendingCount"] == 24
    assert first["items"][0]["hasResult"] is True
    assert first["items"][0]["durationMs"] == 2000
    assert len(json.dumps(first, default=str)) < 30_000
    assert all(
        "input_snapshot_json" not in statement
        and "output_context_json" not in statement
        and "snapshot_json" not in statement
        for statement in sql
    )
    detail = await AiGenerateTaskRepository(session).get_run("run-24")
    assert len(detail.snapshot_json["source"]) == 200_000
    assert len(detail.result_yaml) > 200_000


async def test_history_filter_precedes_pagination_and_preserves_global_latest(database):
    sync, session, _ = database
    seed_history(sync)
    imported = await history_page(session, [Run.task_id == "task"], 1, 10, "imported")
    assert imported["total"] == 1
    assert imported["items"][0]["runId"] == "run-00"
    assert imported["items"][0]["importStatus"] == "imported"
    assert imported["latestRun"]["runId"] == "run-24"
    pending = await history_page(session, [Run.task_id == "task"], 2, 10, "review_pending")
    assert pending["total"] == 24 and len(pending["items"]) == 10


async def test_history_permissions_and_page_bounds(database):
    sync, session, _ = database
    seed_history(sync, 1)
    service = AiGenerateTaskService(AiGenerateTaskRepository(session))
    with pytest.raises(AppError):
        await service.list_run_summaries("function", "task", "outsider")
    with pytest.raises(AppError):
        await service.list_run_summaries("api", "task", "u")
    for page, size in [(0, 20), (1, 0), (1, 101)]:
        with pytest.raises(AppError):
            await service.list_run_summaries("function", "task", "u", page, size)


class CapturingSession:
    async def run_sync(self, operation):
        return operation(self)

    def __init__(self):
        self.statements = []

    async def scalar(self, statement):
        self.statements.append(str(statement.compile(dialect=mysql.dialect())))
        return None


@pytest.mark.parametrize("repository", [AiGenerateTaskRepository, ResourceBindingRepository])
async def test_read_queries_are_unlocked_and_mutations_can_lock(repository):
    session = CapturingSession()
    repo = repository(session)
    for key in ["project", "sprint", "requirement"]:
        await getattr(repo, f"get_{key}")("id")
        assert "FOR UPDATE" not in session.statements[-1]
        await getattr(repo, f"get_{key}_for_update")("id")
        assert "FOR UPDATE" in session.statements[-1]
    if repository is AiGenerateTaskRepository:
        await repo.get_run("id")
        assert "FOR UPDATE" not in session.statements[-1]
        await repo.get_run_for_update("id")
        assert "FOR UPDATE" in session.statements[-1]


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


@pytest.mark.parametrize("size", [1, 100])
async def test_code_risk_case_query_count_does_not_grow_with_cases(database, size):
    sync, session, sql = database
    seed_cases(sync, size)
    service = CodeRiskAnalysisService.__new__(CodeRiskAnalysisService)
    service.task_repository = AiGenerateTaskRepository(session)
    sql.clear()
    function = await service._function_cases("req")
    api = await service._api_cases("req")
    ui = await service._ui_cases("req")
    assert len(function) == len(api) == len(ui) == size
    assert len(sql) == 6  # function 1, API 3, UI 2, independent of case count
    assert all(row["lastRun"]["status"] == "success" for row in [*api, *ui])
    assert all(row["caseId"] != "foreign-api" for row in api)
    assert all(
        "private_payload" not in statement
        and "request_snapshot_json" not in statement
        and "step_results_json" not in statement
        for statement in sql
    )


async def test_daily_metrics_return_only_latest_status_and_counts(database):
    sync, session, sql = database
    seed_cases(sync, 3)
    sql.clear()
    repo = SprintDailyMetricsRepository(session)
    assert await repo.list_latest_api_run_statuses("s") == {f"api-{i}": "success" for i in range(3)}
    ui = await repo.list_latest_ui_suite_runs("s")
    assert len(ui) == 1 and ui[0].success_count == 2 and ui[0].total_count == 3
    assert len(sql) == 2
    assert all(
        "private_payload" not in statement and "snapshot_json" not in statement for statement in sql
    )


async def test_ai_task_scope_checks_are_batched_without_loading_requirement_documents(database):
    sync, session, sql = database
    task = sync.scalar(select(AiGenerateTask))
    sql.clear()
    repo = AiGenerateTaskRepository(session)
    scopes = await repo.task_scope_resources([task] * 40)
    service = AiGenerateTaskService(repo)
    for row in [task] * 40:
        await service.validate_task_scope(row, scopes)
    assert len(sql) == 2
    assert all("document_content" not in query and "FOR UPDATE" not in query for query in sql)


@pytest.mark.asyncio
async def test_bug_snapshot_uses_project_and_found_sprint_without_pagination(db):  # noqa: F811
    from testing_agent.models.bug import Bug
    from testing_agent.models.project import Project

    db.add(Project(project_id="other-project", user_id="u", name="other"))
    db.flush()
    for i in range(105):
        db.add(
            Bug(
                bug_id=f"b{i}",
                bug_no=i + 1,
                project_id="p",
                title=f"Bug {i}",
                found_sprint_id="s",
                status="active",
                severity="normal",
            )
        )
    db.add_all(
        [
            Bug(
                bug_id="planned",
                bug_no=106,
                project_id="p",
                title="Only planned",
                found_sprint_id="other",
                planned_fix_sprint_id="s",
            ),
            Bug(
                bug_id="foreign",
                bug_no=1,
                project_id="other-project",
                title="Foreign",
                found_sprint_id="s",
            ),
        ]
    )
    db.flush()
    rows = await SprintDailyMetricsRepository(AsyncAdapter(db)).list_bug_snapshots("p", "s")
    assert len(rows) == 105
    assert {row["bugId"] for row in rows} == {f"b{i}" for i in range(105)}
    assert "description_html" not in rows[0]
