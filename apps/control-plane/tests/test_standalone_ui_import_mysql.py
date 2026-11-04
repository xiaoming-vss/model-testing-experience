"""UI candidate import preserves formal assets and provenance on MySQL."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.standalone_execution import start_standalone_execution
from testing_agent.services.standalone_execution_view import project_standalone_execution
from testing_agent.services.ui_generate_import import import_ui_run


async def test_ui_import_conflict_and_provenance(mysql):  # noqa: F811
    with mysql.begin() as connection:
        suite = seed_row(connection, UiTestSuite.__table__)
        project_id = connection.scalar(
            sa.select(Sprint.project_id)
            .join(Requirement, Requirement.sprint_id == Sprint.sprint_id)
            .where(Requirement.requirement_id == suite["requirement_id"])
        )
        case = seed_row(
            connection,
            UiTestCase.__table__,
            {"suite_id": suite["suite_id"], "name": "Login", "steps_json": []},
        )
        task = seed_row(
            connection,
            AiGenerateTask.__table__,
            {
                "task_type": "ui_case_generate",
                "project_id": project_id,
                "sprint_id": "",
                "requirement_id": "",
            },
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    statements = []
    sa.event.listen(
        engine.sync_engine,
        "before_cursor_execute",
        lambda _c, _u, sql, _p, _x, _m: statements.append(sql.lower()),
    )
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            task_row = await session.scalar(
                sa.select(AiGenerateTask).where(AiGenerateTask.task_id == task["task_id"])
            )
            execution, attempt, _ = await start_standalone_execution(
                session,
                task=task_row,
                execution_id="ui-import-run",
                request_id="ui-import-worker",
                actor_id="user",
                connection_id="llm",
                source={"uiWorkflowVersion": "ui_three_stage/1.0"},
                config={},
                checkpoint_enabled=True,
            )
            stage = await session.get(AiGenerationStage, attempt.stage_id)
            stage.stage = "ui_yaml"
            execution.workflow_status, execution.current_stage = "success", "completed"
            attempt.status, attempt.review_status = "success", "approved"
            attempt.reviewer_user_id, attempt.reviewed_at = "reviewer", datetime.now(UTC)
            attempt.output_content = """- name: Login
  enabled: true
  orderNo: 1
  stepsJson:
  - orderNo: 1
    stepName: Open
    keyword: open
    operationValue: https://example.test/new
    continueOnFailure: false
    enabled: true
"""
            attempt.output_format = "yaml"
            await session.commit()
            view = await project_standalone_execution(session, execution.execution_id)
            context = SimpleNamespace(
                repository=AiGenerateTaskRepository(session),
                owned_run=AsyncMock(return_value=view),
                ensure_requirement_access=AsyncMock(),
            )
            preview = await import_ui_run(
                context, "ui-import-run", suite["suite_id"], False, "user"
            )
            assert preview["requiresConfirmation"]
            result = await import_ui_run(context, "ui-import-run", suite["suite_id"], True, "user")
            assert result["run"]["importStatus"] == "imported"
            updated = await session.scalar(
                sa.select(UiTestCase)
                .where(UiTestCase.case_id == case["case_id"])
                .execution_options(populate_existing=True)
            )
            assert updated.steps_json[0]["operationValue"] == "https://example.test/new"
            record = await session.scalar(
                sa.select(AiGenerateVersionImport).where(
                    AiGenerateVersionImport.attempt_id == attempt.id
                )
            )
            target = await session.scalar(
                sa.select(UiTestSuite)
                .where(UiTestSuite.suite_id == suite["suite_id"])
                .execution_options(populate_existing=True)
            )
            assert record is not None and target.effective_import_id == record.import_id
            assert not any(
                table in sql
                for sql in statements
                for table in (
                    "ai_generate_task_runs",
                    "ai_generate_run_stages",
                    "ai_generate_stage_attempts",
                    "ai_generate_run_imports",
                )
            )
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(
                sa.delete(WorkerTask).where(WorkerTask.task_id == "ui-import-worker")
            )
            connection.execute(
                sa.delete(AiGenerateTask).where(AiGenerateTask.task_id == task["task_id"])
            )
            connection.execute(
                sa.delete(UiTestCase).where(UiTestCase.suite_id == suite["suite_id"])
            )
            connection.execute(
                sa.delete(UiTestSuite).where(UiTestSuite.suite_id == suite["suite_id"])
            )
