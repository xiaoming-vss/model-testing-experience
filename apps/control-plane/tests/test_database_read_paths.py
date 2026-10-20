"""SQL/result contracts for bounded histories and batched snapshot reads."""

import json

import pytest
from sqlalchemy import select
from support.ai_execution import db  # noqa: F401
from support.database_read_paths import (
    NOW as NOW,
)
from support.database_read_paths import (
    AsyncAdapter as AsyncAdapter,
)
from support.database_read_paths import (
    CapturingSession as CapturingSession,
)
from support.database_read_paths import (
    database as database,
)
from support.database_read_paths import (
    seed_cases as seed_cases,
)
from support.database_read_paths import (
    seed_history as seed_history,
)

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generate_task import AiGenerateTaskRun as Run
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.ai_generate_task_source_archive import (
    AiGenerateTaskSourceArchiveRepository,
)
from testing_agent.repositories.ai_run_history import history_page
from testing_agent.repositories.resource_binding import ResourceBindingRepository
from testing_agent.repositories.sprint_daily_metrics import SprintDailyMetricsRepository
from testing_agent.services.ai_task_queries import GenerationQueries
from testing_agent.services.ai_task_scope import GenerationAccess
from testing_agent.services.code_risk_analysis import CodeRiskAnalysisService


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
    repository = AiGenerateTaskRepository(session)
    service = GenerationQueries(
        repository, AiGenerateTaskSourceArchiveRepository(session), GenerationAccess(repository)
    )
    with pytest.raises(AppError):
        await service.list_run_summaries("function", "task", "outsider")
    with pytest.raises(AppError):
        await service.list_run_summaries("api", "task", "u")
    for page, size in [(0, 20), (1, 0), (1, 101)]:
        with pytest.raises(AppError):
            await service.list_run_summaries("function", "task", "u", page, size)


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
    service = GenerationAccess(repo)
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


async def test_run_detail_keeps_artifact_and_scope_while_history_stays_compact(database):
    sync, session, _ = database
    seed_history(sync, 1)
    repository = AiGenerateTaskRepository(session)
    queries = GenerationQueries(
        repository, AiGenerateTaskSourceArchiveRepository(session), GenerationAccess(repository)
    )
    with pytest.raises(AppError):
        await queries.get_run("function", "run-00", "outsider")
    detail = await queries.get_run("function", "run-00", "u")
    assert detail["runId"] == "run-00"
    assert detail["resultYaml"] == "cases: " + "Y" * 200_000
    assert detail["snapshotJson"] == {"source": "X" * 200_000}
    history = await queries.list_run_summaries("function", "task", "u")
    assert history["items"][0]["hasResult"] is True
    assert "resultYaml" not in history["items"][0]
    assert "snapshotJson" not in history["items"][0]
