"""SQL/result contracts for bounded histories and batched snapshot reads."""

import json
from datetime import timedelta

import pytest
from sqlalchemy import select
from support.ai_execution import db as db  # noqa: F401
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

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.test_order import TestOrder as OrderModel
from testing_agent.models.ui_test_case_run import UiTestCaseRun
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.api_collection_run import ApiCollectionRunRepository
from testing_agent.repositories.resource_binding import ResourceBindingRepository
from testing_agent.repositories.sprint_daily_metrics import SprintDailyMetricsRepository
from testing_agent.services.ai_task_scope import GenerationAccess
from testing_agent.services.code_risk_analysis import CodeRiskAnalysisService


@pytest.mark.parametrize("size", [1, 100])
async def test_api_report_related_reads_are_batched(database, size):
    sync, session, sql = database
    seed_cases(sync, size)
    repository = ApiCollectionRunRepository(session)
    sql.clear()
    cases = await repository.report_cases([f"api-{i}" for i in range(size)])
    runs = await repository.report_case_runs([f"api-{i}-0" for i in range(size)])
    assert len(cases) == len(runs) == size
    assert len(sql) == 2
    assert cases["api-0"].name == "api-0"
    assert runs["api-0-0"].request_snapshot_json is None
    assert "api_cases.body_json" not in sql[0].lower()
    assert "api_cases.body_text" not in sql[0].lower()
    assert "api_case_runs.private_payload" not in sql[1].lower()
    sql.clear()
    assert await repository.report_cases([]) == {}
    assert await repository.report_case_runs([]) == {}
    assert not sql


@pytest.mark.parametrize("repository", [AiGenerateTaskRepository, ResourceBindingRepository])
async def test_read_queries_are_unlocked_and_mutations_can_lock(repository):
    session = CapturingSession()
    repo = repository(session)
    for key in ["project", "sprint", "requirement"]:
        await getattr(repo, f"get_{key}")("id")
        assert "FOR UPDATE" not in session.statements[-1]
        await getattr(repo, f"get_{key}_for_update")("id")
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


async def test_private_live_debug_does_not_replace_shared_latest_run_or_metrics(database):
    sync, session, _ = database
    seed_cases(sync, 1)
    sync.add_all(
        [
            ApiCaseRun(
                run_id="api-private",
                case_id="api-0",
                collection_id="ac",
                environment_id="e",
                trigger_user_id="u",
                trigger_type="live_debug",
                status="error",
                created_at=NOW,
            ),
            UiTestCaseRun(
                run_id="ui-private",
                case_id="ui-0",
                suite_id="uc",
                trigger_user_id="u",
                trigger_type="live_debug",
                status="error",
                created_at=NOW,
            ),
        ]
    )
    sync.commit()
    repo = AiGenerateTaskRepository(session)
    assert (await repo.latest_case_run_summaries(["api-0"], "api"))["api-0"].status == "success"
    assert (await repo.latest_case_run_summaries(["ui-0"], "ui"))["ui-0"].status == "success"
    assert (await repo.get_latest_api_case_run("api-0")).run_id == "api-0-1"
    assert (await repo.get_latest_ui_case_run("ui-0")).run_id == "ui-0-1"
    assert await SprintDailyMetricsRepository(session).list_latest_api_run_statuses("s") == {
        "api-0": "success"
    }


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


@pytest.mark.parametrize("size", [1, 100])
async def test_ai_task_list_reads_are_batched(database, size):
    sync, session, sql = database
    sync.add_all(
        [
            AiGenerateTask(
                task_id=f"code-risk-task-{index}",
                task_type="code_risk_analysis",
                name=f"code-risk-task-{index}",
                project_id="p",
                sprint_id="s",
                requirement_id="req",
                creator_user_id="u",
                source_type="text",
                source_content="secret-body",
                created_at=NOW,
            )
            for index in range(size)
        ]
    )
    sync.commit()
    sql.clear()
    repo = AiGenerateTaskRepository(session)
    total = await repo.count_tasks("p", "code_risk_analysis")
    rows = await repo.list_tasks_page("p", "code_risk_analysis", page=1, page_size=20)
    counts = await repo.task_status_counts("p", "code_risk_analysis")

    assert total == size
    assert len(rows) == min(size, 20)
    assert sum(counts.values()) == size
    assert len(sql) == 3
    assert all("test_orders" not in query and "document_content" not in query for query in sql)


async def test_ai_task_scope_batches_test_order_lookups(database):
    sync, session, sql = database
    sync.add_all(
        [
            OrderModel(
                order_id=f"order-{index}",
                project_id="p",
                sprint_id="s",
                name=f"order-{index}",
            )
            for index in range(40)
        ]
    )
    sync.add_all(
        [
            AiGenerateTask(
                task_id=f"order-task-{index}",
                task_type="test_order_graph",
                name=f"order-task-{index}",
                project_id="p",
                sprint_id="s",
                requirement_id="req",
                order_id=f"order-{index}",
                creator_user_id="u",
                source_type="text",
                source_content="input",
            )
            for index in range(40)
        ]
    )
    sync.commit()
    tasks = list(
        sync.scalars(select(AiGenerateTask).where(AiGenerateTask.task_type == "test_order_graph"))
    )
    sql.clear()
    repo = AiGenerateTaskRepository(session)
    scopes = await repo.task_scope_resources(tasks)
    service = GenerationAccess(repo)
    for task in tasks:
        await service.validate_task_scope(task, scopes)

    assert len(sql) == 3
    assert sum("FROM test_orders" in query for query in sql) == 1
    assert not any("test_orders.order_id = ?" in query for query in sql)
    assert all("FOR UPDATE" not in query for query in sql)


async def test_ai_task_scope_rejects_invalid_order_bindings(database):
    sync, session, _ = database
    sync.add_all(
        [
            Project(project_id="other", user_id="u", name="other"),
            Sprint(
                sprint_id="s2",
                project_id="p",
                name="s2",
                start_time=NOW,
                end_time=NOW + timedelta(days=1),
            ),
        ]
    )
    sync.flush()
    sync.add_all(
        [
            Requirement(requirement_id="req2", sprint_id="s2", name="req2"),
            OrderModel(
                order_id="foreign-project",
                project_id="other",
                sprint_id="s",
                name="foreign-project",
            ),
            OrderModel(
                order_id="foreign-sprint",
                project_id="p",
                sprint_id="s2",
                name="foreign-sprint",
            ),
        ]
    )
    sync.flush()
    tasks = [
        AiGenerateTask(
            task_id="missing-order-task",
            task_type="test_order_graph",
            name="missing-order-task",
            project_id="p",
            sprint_id="s",
            requirement_id="req",
            order_id="missing-order",
            creator_user_id="u",
            source_type="text",
            source_content="input",
        ),
        AiGenerateTask(
            task_id="foreign-project-task",
            task_type="test_order_graph",
            name="foreign-project-task",
            project_id="p",
            sprint_id="s",
            requirement_id="req",
            order_id="foreign-project",
            creator_user_id="u",
            source_type="text",
            source_content="input",
        ),
        AiGenerateTask(
            task_id="foreign-sprint-task",
            task_type="test_order_graph",
            name="foreign-sprint-task",
            project_id="p",
            sprint_id="s",
            requirement_id="req",
            order_id="foreign-sprint",
            creator_user_id="u",
            source_type="text",
            source_content="input",
        ),
        AiGenerateTask(
            task_id="requirement-sprint-mismatch-task",
            task_type="test_order_graph",
            name="requirement-sprint-mismatch-task",
            project_id="p",
            sprint_id="s",
            requirement_id="req2",
            creator_user_id="u",
            source_type="text",
            source_content="input",
        ),
    ]
    sync.add_all(tasks)
    sync.commit()
    repo = AiGenerateTaskRepository(session)
    service = GenerationAccess(repo)
    scopes = await repo.task_scope_resources(tasks)

    with pytest.raises(AppError) as missing:
        await service.validate_task_scope(tasks[0], scopes)
    assert missing.value.code == 404
    with pytest.raises(AppError) as foreign_project:
        await service.validate_task_scope(tasks[1], scopes)
    assert foreign_project.value.code == 404
    with pytest.raises(AppError) as foreign_sprint:
        await service.validate_task_scope(tasks[2], scopes)
    assert foreign_sprint.value.code == 404
    with pytest.raises(AppError) as mismatch:
        await service.validate_task_scope(tasks[3], scopes)
    assert mismatch.value.code == 400


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


async def test_selected_function_export_batches_sql_and_preserves_requested_order(database):
    from testing_agent.models.function_test_case import FunctionTestCase
    from testing_agent.models.function_test_suite import FunctionTestSuite
    from testing_agent.repositories.function_test_case import FunctionTestCaseRepository
    from testing_agent.services.function_case_export import FunctionCaseExporter

    sync, session, sql = database
    sync.add(FunctionTestSuite(suite_id="export-suite", requirement_id="req", name="export"))
    sync.flush()
    sync.add_all(
        [
            FunctionTestCase(
                case_id=f"export-{i}",
                suite_id="export-suite",
                title=f"case {i}",
                content_json={"preconditions": [], "steps": []},
            )
            for i in range(1201)
        ]
    )
    sync.commit()
    exporter = FunctionCaseExporter(FunctionTestCaseRepository(session))
    selected = [f"export-{i}" for i in reversed(range(1201))]
    sql.clear()
    result = await exporter.resolve_cases_for_zentao_import("export-suite", selected)
    assert [case.case_id for case in result] == selected
    assert len(sql) == 3 and all(" IN (" in statement for statement in sql)
    sql.clear()
    with pytest.raises(AppError, match="重复"):
        await exporter.resolve_cases_for_zentao_import("export-suite", ["export-0", " export-0 "])
    assert not sql
    with pytest.raises(AppError, match="不能为空"):
        await exporter.resolve_cases_for_zentao_import("export-suite", ["export-0", " "])
    assert not sql
    with pytest.raises(AppError) as missing:
        await exporter.resolve_cases_for_zentao_import("export-suite", ["missing"])
    assert missing.value.http_code == 404
    with pytest.raises(AppError, match="不属于当前测试集"):
        await exporter.resolve_cases_for_zentao_import("foreign-suite", ["export-0"])


async def test_order_entry_pages_project_summaries_and_preserve_focus_and_counts(database):
    from testing_agent.domain.test_order_query import EntryQuery
    from testing_agent.models.function_test_case import FunctionTestCase
    from testing_agent.models.function_test_suite import FunctionTestSuite
    from testing_agent.models.test_order import TestOrder
    from testing_agent.models.test_order_entry import TestOrderEntry
    from testing_agent.repositories.test_order_reads import TestOrderReadRepository

    sync, session, sql = database
    sync.add(FunctionTestSuite(suite_id="page-suite", requirement_id="req", name="pages"))
    sync.add_all(
        [
            TestOrder(order_id=key, project_id="p", sprint_id="s", name=key)
            for key in ("order", "foreign")
        ]
    )
    sync.flush()
    body = {"preconditions": ["BODY" * 10000], "steps": []}
    sync.add_all(
        [
            FunctionTestCase(
                case_id=f"page-{i}",
                suite_id="page-suite",
                title=f"case {i}",
                module="50%_done" if i == 50 else "module",
                content_json=body,
            )
            for i in range(52)
        ]
    )
    sync.flush()
    sync.add_all(
        [
            TestOrderEntry(
                entry_id=f"entry-{i}",
                order_id="order" if i < 51 else "foreign",
                case_id=f"page-{i}",
                order_no=i // 2,
                snapshot_json=body,
                status="passed" if i < 35 else "pending",
                assignee_user_id="u" if i % 2 == 0 else "",
            )
            for i in range(52)
        ]
    )
    sync.commit()
    reader = TestOrderReadRepository(session)
    sql.clear()
    first = await reader.page("order", "u", EntryQuery())
    assert first["total"] == first["orderTotal"] == 51
    assert first["mineCount"] == 26 and len(first["items"]) == 20
    assert [row["entry_id"] for row in first["items"]] == [f"entry-{i}" for i in range(20)]
    assert first["statusCounts"] == {
        "pending": 16,
        "passed": 35,
        "failed": 0,
        "blocked": 0,
        "skipped": 0,
    }
    assert len(sql) == 3
    assert all(
        "snapshot_json" not in statement and "content_json" not in statement for statement in sql
    )
    assert len(json.dumps(first, default=str)) < 18000
    assert all("snapshot" not in row for row in first["items"])
    resumed = await reader.page("order", "u", EntryQuery(resume=True))
    assert resumed["page"] == 2 and resumed["preferredEntryId"] == "entry-35"
    focused = await reader.page("order", "u", EntryQuery(focus_entry_id="entry-50"))
    assert focused["page"] == 3 and focused["preferredEntryId"] == "entry-50"
    following = await reader.page("order", "u", EntryQuery(resume=True, after_entry_id="entry-35"))
    assert following["preferredEntryId"] == "entry-36"
    assert (await reader.page("order", "u", EntryQuery(resume=True, after_entry_id="entry-50")))[
        "preferredEntryId"
    ] == ""
    assert (await reader.page("order", "u", EntryQuery(page=999)))["page"] == 3
    mine = await reader.page("order", "u", EntryQuery(only_mine=True, status="pending"))
    assert mine["total"] == 8 and mine["matchedTotal"] == 26 and mine["mineCount"] == 26
    literal = await reader.page("order", "u", EntryQuery(keyword="%_"))
    assert literal["total"] == 1 and literal["items"][0]["entry_id"] == "entry-50"
    assert (await reader.page("order", "u", EntryQuery(keyword="no-match")))["total"] == 0
    assert [
        row["entry_id"] for row in await reader.lookup("order", ["page-0", "page-50", "page-51"])
    ] == ["entry-0", "entry-50"]
    assert await reader.detail("order", "entry-51") is None
    detail = await reader.detail("order", "entry-0")
    assert detail["snapshot"] == body


async def test_export_manifest_bounds_bodies_and_defers_late_batch_failures(database):
    from types import SimpleNamespace

    from testing_agent.domain.integration_execution import digest
    from testing_agent.models.function_test_case import FunctionTestCase
    from testing_agent.models.function_test_suite import FunctionTestSuite
    from testing_agent.repositories.function_test_case import FunctionTestCaseRepository
    from testing_agent.schemas.function_test_case import ImportFunctionCasesToZentaoRequest
    from testing_agent.services.function_case_export import FunctionCaseExporter
    from testing_agent.services.function_case_push_flow import CasePushScope

    sync, session, sql = database
    sync.add(FunctionTestSuite(suite_id="bounded", requirement_id="req", name="bounded"))
    sync.flush()
    sync.add_all(
        [
            FunctionTestCase(
                case_id=f"body-{i}",
                suite_id="bounded",
                title=f"case {i}",
                order_no=i,
                content_json={
                    "preconditions": [],
                    "steps": [{"action": "A" * 4096, "expected": "E" * 4096}],
                },
            )
            for i in range(1001)
        ]
    )
    sync.commit()
    sizes = []

    class MeasuredRepository(FunctionTestCaseRepository):
        async def list_cases_by_ids(self, case_ids):
            sizes.append(len(case_ids))
            return await super().list_cases_by_ids(case_ids)

    writes = []

    class Flow:
        async def push_one(
            self, actor, scope, gateway, *, case_id, payload, expected_payload_digest, **kwargs
        ):
            if digest(payload) != expected_payload_digest:
                raise AppError(409, "内容已变化", 409)
            writes.append(case_id)
            if case_id == "body-499":
                # A later batch changes after admission: preserve earlier receipts, reject that row.
                row = sync.scalar(
                    select(FunctionTestCase).where(FunctionTestCase.case_id == "body-501")
                )
                row.title = "changed after admission"
                sync.commit()
            return {"caseId": case_id, "status": "success", "remoteCaseId": len(writes)}

    exporter = FunctionCaseExporter(MeasuredRepository(session), push_flow=Flow())
    scope = CasePushScope(
        "p",
        "bounded",
        "req",
        "s",
        SimpleNamespace(),
        {"productID": 1, "project": 2, "execution": 3, "story": 4, "module": 0},
    )
    sql.clear()
    references = await exporter.resolve_cases_for_zentao_import("bounded", [])
    assert [row.case_id for row in references] == [f"body-{i}" for i in range(1001)]
    assert len(sql) == 1 and "content_json" not in sql[0] and "steps" not in sql[0]
    identifiers = [row.case_id for row in references]
    manifest = await exporter.prepare_manifest(scope, identifiers)
    assert sizes == [500, 500, 1]
    assert all(set(value) == {"suiteId", "digest", "order"} for value in manifest.values())
    assert len(json.dumps(manifest)) < 160_000
    sizes.clear()
    result = await exporter.push_suite(
        "u", scope, ImportFunctionCasesToZentaoRequest(productId=1), None, manifest, "fingerprint"
    )
    assert sizes == [500, 500]  # No body reads after the first changed item stops the push.
    assert writes == identifiers[:501]
    assert result["items"][501]["status"] == "failed"
    assert result["items"][501]["caseId"] == "body-501"
    assert all(item["status"] == "skipped" for item in result["items"][502:])
    # A malformed final item must fail the complete preflight, before any push is admitted.
    last = sync.scalar(select(FunctionTestCase).where(FunctionTestCase.case_id == "body-1000"))
    last.content_json = {"preconditions": [], "steps": []}
    sync.commit()
    with pytest.raises(AppError, match="测试步骤不能为空"):
        await exporter.prepare_manifest(scope, identifiers)
    assert writes == identifiers[:501]
