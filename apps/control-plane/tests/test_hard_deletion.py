"""Deletion contract against a real database with foreign keys enabled."""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event, func, select
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from testing_agent import models as m
from testing_agent.core.errors import AppError
from testing_agent.repositories.deletion import delete_resource


@compiles(LONGTEXT, "sqlite")
def longtext_sqlite(type_, compiler, **kw):
    return "TEXT"


@pytest_asyncio.fixture
async def db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'delete.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(m.Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        await add(session, m.User(user_id="u", nickname="user"))
        await add(session, m.Project(project_id="p", user_id="u", name="project"))
        now = datetime.now(UTC)
        await add(
            session,
            m.Sprint(
                sprint_id="s",
                project_id="p",
                name="sprint",
                start_time=now,
                end_time=now + timedelta(days=1),
            ),
        )
        await add(
            session,
            m.Requirement(
                requirement_id="r",
                sprint_id="s",
                name="req",
                document_type="text",
                document_content="",
            ),
        )
        await session.commit()
        yield session
    await engine.dispose()


async def add(db, obj):
    db.add(obj)
    await db.flush()
    return obj


async def count(db, model):
    return await db.scalar(select(func.count()).select_from(model))


@pytest.mark.parametrize(
    "suite_model,case_model,case_args",
    [
        (m.FunctionTestSuite, m.FunctionTestCase, {"title": "case"}),
        (m.UiTestSuite, m.UiTestCase, {"name": "case", "steps_json": []}),
        (m.ApiCollection, m.ApiCase, {"name": "case", "method": "GET", "url_template": "/"}),
    ],
)
async def test_child_first_and_name_reuse(db, suite_model, case_model, case_args):
    key = "collection_id" if suite_model is m.ApiCollection else "suite_id"
    suite = await add(db, suite_model(**{key: "suite"}, requirement_id="r", name="same"))
    case = await add(db, case_model(**{key: "suite"}, case_id="case", **case_args))
    await db.commit()
    with pytest.raises(AppError) as blocked:
        await delete_resource(db, suite)
    assert blocked.value.http_code == 409
    assert blocked.value.data["blockers"][0]["count"] == 1
    assert await count(db, case_model) == 1
    await delete_resource(db, case)
    await delete_resource(db, suite)
    await db.commit()
    assert await count(db, case_model) == 0
    assert await count(db, suite_model) == 0
    await add(db, suite_model(**{key: "new"}, requirement_id="r", name="same"))
    await db.commit()


async def test_database_prevents_bypassing_child_guard(db):
    suite = await add(db, m.FunctionTestSuite(suite_id="suite", requirement_id="r", name="suite"))
    await add(db, m.FunctionTestCase(case_id="case", suite_id="suite", title="case"))
    await db.commit()
    await db.delete(suite)
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()
    assert await count(db, m.FunctionTestSuite) == 1


async def test_api_case_cleans_rules_runs_and_queue(db):
    await add(db, m.ApiCollection(collection_id="col", requirement_id="r", name="api"))
    case = await add(
        db,
        m.ApiCase(case_id="case", collection_id="col", name="case", method="GET", url_template="/"),
    )
    await add(
        db,
        m.ApiAssertRule(
            assert_rule_id="a",
            case_id="case",
            name="status",
            assert_source="status_code",
            comparator="eq",
        ),
    )
    await add(
        db,
        m.ApiExtractRule(
            extract_rule_id="e", case_id="case", name="token", source="body", var_key="token"
        ),
    )
    await add(
        db,
        m.ApiCollectionRun(
            collection_run_id="cr", collection_id="col", environment_id="env", trigger_user_id="u"
        ),
    )
    await add(
        db,
        m.ApiCaseRun(
            run_id="run",
            case_id="case",
            collection_id="col",
            collection_run_id="cr",
            environment_id="env",
            trigger_user_id="u",
        ),
    )
    await add(
        db,
        m.ApiCollectionRunItem(
            item_id="i", collection_run_id="cr", case_id="case", case_run_id="run"
        ),
    )
    await add(
        db,
        m.WorkerTask(
            task_id="w", domain="api", task_type="api_case", run_id="run", status="running"
        ),
    )
    await db.commit()
    await delete_resource(db, case)
    await db.commit()
    for model in (
        m.ApiCase,
        m.ApiAssertRule,
        m.ApiExtractRule,
        m.ApiCaseRun,
        m.ApiCollectionRunItem,
        m.WorkerTask,
    ):
        assert await count(db, model) == 0
    assert await count(db, m.ApiCollection) == 1


async def test_ai_task_cleans_normalized_results_and_source_after_commit(db, tmp_path):
    task = await add(
        db,
        m.AiGenerateTask(
            task_id="task",
            task_type="ui_case_generate",
            name="task",
            project_id="p",
            sprint_id="s",
            requirement_id="r",
            creator_user_id="u",
            source_type="manual",
            source_content="",
        ),
    )
    await add(db, m.AiGenerateTaskRun(run_id="run", task_id="task", trigger_user_id="u"))
    await add(db, m.AiGenerateRunStage(id="stage", run_id="run", stage="generate", stage_order=1))
    await add(
        db,
        m.AiGenerateStageAttempt(
            id="attempt", stage_id="stage", attempt_no=1, operation="generate", status="succeeded"
        ),
    )
    await add(
        db,
        m.AiGenerateRunImport(
            id="import", run_id="run", artifact_attempt_id="attempt", idempotency_key="once"
        ),
    )
    await add(db, m.WorkerTask(task_id="worker", domain="ai", task_type="generate", run_id="run"))
    source = tmp_path / "source.zip"
    source.write_bytes(b"source")
    await add(
        db,
        m.AiGenerateTaskSourceArchive(
            archive_id="archive",
            task_id="task",
            filename="source.zip",
            size_bytes=6,
            sha256="hash",
            storage_path=str(source),
            uploaded_at=datetime.now(UTC),
        ),
    )
    await db.commit()
    await delete_resource(db, task)
    assert source.exists()
    await db.commit()
    assert not source.exists()
    for model in (
        m.AiGenerateTask,
        m.AiGenerateTaskRun,
        m.AiGenerateRunStage,
        m.AiGenerateStageAttempt,
        m.AiGenerateRunImport,
        m.AiGenerateTaskSourceArchive,
        m.WorkerTask,
    ):
        assert await count(db, model) == 0


async def test_ai_run_deletes_its_own_stages_and_queue_only(db):
    await add(
        db,
        m.AiGenerateTask(
            task_id="task",
            task_type="api_case_generate",
            name="task",
            project_id="p",
            sprint_id="s",
            requirement_id="r",
            creator_user_id="u",
            source_type="manual",
            source_content="",
        ),
    )
    for run_id in ("run", "other"):
        await add(db, m.AiGenerateTaskRun(run_id=run_id, task_id="task", trigger_user_id="u"))
    await add(db, m.AiGenerateRunStage(id="stage", run_id="run", stage="generate", stage_order=1))
    await add(
        db,
        m.AiGenerateStageAttempt(
            id="attempt", stage_id="stage", attempt_no=1, operation="generate", status="succeeded"
        ),
    )
    await add(
        db,
        m.AiGenerateRunImport(
            id="import", run_id="run", artifact_attempt_id="attempt", idempotency_key="once"
        ),
    )
    await add(db, m.WorkerTask(task_id="worker", domain="ai", task_type="generate", run_id="run"))
    await db.commit()
    run = await db.scalar(select(m.AiGenerateTaskRun).where(m.AiGenerateTaskRun.run_id == "run"))
    await delete_resource(db, run)
    await db.commit()
    for model in (
        m.AiGenerateRunStage,
        m.AiGenerateStageAttempt,
        m.AiGenerateRunImport,
        m.WorkerTask,
    ):
        assert await count(db, model) == 0
    assert await count(db, m.AiGenerateTask) == 1
    assert await count(db, m.AiGenerateTaskRun) == 1


async def test_rollback_keeps_file_and_resource(db, tmp_path):
    source = tmp_path / "req.txt"
    source.write_text("requirement")
    req = await db.scalar(select(m.Requirement))
    req.document_storage_path = str(source)
    await db.commit()
    await delete_resource(db, req)
    await db.rollback()
    await db.commit()
    assert source.exists()
    assert await count(db, m.Requirement) == 1


async def test_hierarchy_blocks_then_can_be_deleted_leaf_to_root(db):
    req = await db.scalar(select(m.Requirement))
    sprint = await db.scalar(select(m.Sprint))
    project = await db.scalar(select(m.Project))
    for parent in (project, sprint):
        with pytest.raises(AppError, match="请先删除"):
            await delete_resource(db, parent)
    for obj in (req, sprint, project):
        await delete_resource(db, obj)
    await db.commit()
    for model in (m.Requirement, m.Sprint, m.Project):
        assert await count(db, model) == 0


async def test_environment_removes_owned_variables(db):
    env = await add(db, m.ApiEnvironment(environment_id="env", project_id="p", name="dev"))
    await add(db, m.ApiEnvironmentVar(env_var_id="v", environment_id="env", var_key="token"))
    await db.commit()
    await delete_resource(db, env)
    await db.commit()
    assert await count(db, m.ApiEnvironmentVar) == 0
    assert await count(db, m.ApiEnvironment) == 0


async def test_shared_service_removes_all_authorizations_and_connections(db):
    from types import SimpleNamespace

    from testing_agent.services.shared_service import SharedServiceService

    service = await add(
        db,
        m.SharedService(
            service_id="service",
            project_id="p",
            provider="llm",
            name="llm",
            base_url="http://example",
        ),
    )
    await add(
        db,
        m.IntegrationConnection(
            connection_id="conn", user_id="u", provider="llm", name="personal", project_id="p"
        ),
    )
    await add(db, m.ServiceAuthorization(service_id="service", user_id="u", connection_id="conn"))
    await db.commit()
    facade = SharedServiceService(SimpleNamespace(repository=SimpleNamespace(session=db)))
    await facade.delete("u", "p", "llm", service.service_id)
    for model in (m.SharedService, m.ServiceAuthorization, m.IntegrationConnection):
        assert await count(db, model) == 0


async def test_ui_case_deletes_aggregate_history_and_worker_without_deleting_suite(db):
    await add(db, m.UiTestSuite(suite_id="suite", requirement_id="r", name="UI"))
    case = await add(db, m.UiTestCase(case_id="case", suite_id="suite", name="case", steps_json=[]))
    await add(
        db, m.UiTestCaseRun(run_id="run", case_id="case", suite_id="suite", trigger_user_id="u")
    )
    await add(db, m.UiTestSuiteRun(suite_run_id="sr", suite_id="suite", trigger_user_id="u"))
    await add(db, m.UiTestSuiteRunItem(item_id="i", suite_run_id="sr", case_id="case"))
    for key in ("run", "sr"):
        await add(db, m.WorkerTask(task_id=key, domain="ui", task_type="ui", run_id=key))
    await db.commit()
    await delete_resource(db, case)
    await db.commit()
    for model in (
        m.UiTestCase,
        m.UiTestCaseRun,
        m.UiTestSuiteRun,
        m.UiTestSuiteRunItem,
        m.WorkerTask,
    ):
        assert await count(db, model) == 0
    assert await count(db, m.UiTestSuite) == 1
