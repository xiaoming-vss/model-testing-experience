"""MySQL import provenance references reviewed candidates and preserves assets."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.standalone_execution import start_standalone_execution
from testing_agent.services.standalone_execution_view import project_standalone_execution
from testing_agent.services.standalone_import import ImportChange, record_standalone_import


async def test_mysql_candidate_provenance_retains_official_case(mysql):  # noqa: F811
    with mysql.begin() as connection:
        suite = seed_row(connection, FunctionTestSuite.__table__)
        project_id = connection.scalar(
            sa.select(Sprint.project_id)
            .join(Requirement, Requirement.sprint_id == Sprint.sprint_id)
            .where(Requirement.requirement_id == suite["requirement_id"])
        )
        case = seed_row(connection, FunctionTestCase.__table__, {"suite_id": suite["suite_id"]})
        task = seed_row(
            connection,
            AiGenerateTask.__table__,
            {
                "task_type": "functional_case_generate",
                "sprint_id": "",
                "requirement_id": "",
                "project_id": project_id,
            },
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            locked_task = await session.scalar(
                sa.select(AiGenerateTask)
                .where(AiGenerateTask.task_id == task["task_id"])
                .with_for_update()
            )
            execution, attempt, _ = await start_standalone_execution(
                session,
                task=locked_task,
                execution_id="import-run",
                request_id="import-worker",
                actor_id="actor",
                connection_id="llm",
                source={},
                config={},
                checkpoint_enabled=False,
            )
            stage = await session.get(AiGenerationStage, attempt.stage_id)
            stage.stage = "detailed_cases"
            execution.workflow_status, execution.current_stage = "success", "completed"
            attempt.status, attempt.output_content = "success", '{"cases":[]}'
            attempt.output_format, attempt.review_status = "json", "approved"
            attempt.reviewer_user_id, attempt.reviewed_at = "reviewer", datetime.now(UTC)
            await session.commit()
            records = await record_standalone_import(
                session,
                task=locked_task,
                execution_id="import-run",
                attempt_id=attempt.id,
                actor_id="importer",
                changes=[ImportChange("function_suite", suite["suite_id"], (case["case_id"],))],
            )
            record_id = records[0].import_id
            await session.commit()
        async with sessions() as session:
            view = await project_standalone_execution(session, "import-run")
            target = await session.scalar(
                sa.select(FunctionTestSuite).where(FunctionTestSuite.suite_id == suite["suite_id"])
            )
            record = await session.scalar(
                sa.select(AiGenerateVersionImport).where(
                    AiGenerateVersionImport.import_id == record_id
                )
            )
            assert (
                view.import_status == "imported"
                and view.imported_targets[0]["targetId"] == suite["suite_id"]
            )
            assert (
                target.effective_import_id == record_id
                and record.attempt_id
                and record.version_id is None
            )
            assert await session.scalar(
                sa.select(FunctionTestCase.case_id).where(
                    FunctionTestCase.case_id == case["case_id"]
                )
            )
            from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
            from testing_agent.services.ai_task_commands import GenerationTaskCommands

            queue = await session.scalar(
                sa.select(WorkerTask).where(WorkerTask.task_id == "import-worker")
            )
            queue.status = "success"
            await session.commit()
            owned = await session.scalar(
                sa.select(AiGenerateTask).where(AiGenerateTask.task_id == task["task_id"])
            )
            access = SimpleNamespace(
                owned_task=AsyncMock(return_value=owned), validate_task_scope=AsyncMock()
            )
            commands = GenerationTaskCommands(AiGenerateTaskRepository(session), access)
            assert await commands.delete_run("function", "import-run", "importer") == {}
            session.expire_all()
            assert await session.scalar(
                sa.select(FunctionTestCase.case_id).where(
                    FunctionTestCase.case_id == case["case_id"]
                )
            )
            assert (
                await session.scalar(
                    sa.select(AiGenerateVersionImport.id).where(
                        AiGenerateVersionImport.import_id == record_id
                    )
                )
                is None
            )
            target = await session.scalar(
                sa.select(FunctionTestSuite).where(FunctionTestSuite.suite_id == suite["suite_id"])
            )
            assert target.effective_import_id is None
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(sa.delete(WorkerTask).where(WorkerTask.task_id == "import-worker"))
            connection.execute(sa.delete(AiGenerateTask))


async def test_mysql_api_import_endpoint_preserves_source_and_existing_case(mysql):  # noqa: F811
    from testing_agent.handlers.generation_guards import ensure_legacy_mutation_allowed
    from testing_agent.models.api_case import ApiCase
    from testing_agent.models.api_collection import ApiCollection
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.services.ai_task_scope import GenerationAccess
    from testing_agent.services.api_generate_import import ApiCandidateImporter

    with mysql.begin() as connection:
        collection = seed_row(connection, ApiCollection.__table__)
        project_id = connection.scalar(
            sa.select(Sprint.project_id)
            .join(Requirement, Requirement.sprint_id == Sprint.sprint_id)
            .where(Requirement.requirement_id == collection["requirement_id"])
        )
        case = seed_row(
            connection,
            ApiCase.__table__,
            {
                "collection_id": collection["collection_id"],
                "name": "Login",
                "method": "GET",
                "url_template": "/old",
            },
        )
        task = seed_row(
            connection,
            AiGenerateTask.__table__,
            {
                "task_type": "api_case_generate",
                "sprint_id": "",
                "requirement_id": "",
                "project_id": project_id,
            },
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            repository = AiGenerateTaskRepository(session)
            owned = await repository.get_task_for_update(task["task_id"])
            execution, attempt, _ = await start_standalone_execution(
                session,
                task=owned,
                execution_id="api-import-run",
                request_id="api-import-worker",
                actor_id="actor",
                connection_id="llm",
                source={},
                config={},
                checkpoint_enabled=False,
            )
            execution.workflow_status, execution.current_stage = "success", "completed"
            attempt.status, attempt.review_status = "success", "approved"
            attempt.reviewer_user_id, attempt.reviewed_at = "reviewer", datetime.now(UTC)
            attempt.output_content = (
                "cases:\n  - name: Login\n    method: GET\n    urlTemplate: /new\n"
            )
            attempt.output_format = "yaml"
            queue = await session.scalar(
                sa.select(WorkerTask).where(WorkerTask.task_id == "api-import-worker")
            )
            queue.status = "success"
            await session.commit()
            access = GenerationAccess(repository)
            access.owned_task = AsyncMock(return_value=owned)
            importer = ApiCandidateImporter(
                repository=repository,
                owned_run=access.owned_run,
                ensure_collection_access=AsyncMock(),
            )
            await ensure_legacy_mutation_allowed(
                access.owned_run, "api", "api-import-run", "actor", action="execute"
            )
            preview = await importer.import_api_run(
                "api-import-run", collection["collection_id"], False, "actor"
            )
            assert preview["requiresConfirmation"] and preview["run"]["importStatus"] == "pending"
            done = await importer.import_api_run(
                "api-import-run", collection["collection_id"], True, "actor"
            )
            assert not done["requiresConfirmation"] and done["run"]["importStatus"] == "imported"
            case_row = await session.scalar(
                sa.select(ApiCase).where(ApiCase.case_id == case["case_id"])
            )
            assert case_row.url_template == "/new"
            record = await session.scalar(
                sa.select(AiGenerateVersionImport).where(
                    AiGenerateVersionImport.attempt_id == attempt.id
                )
            )
            assert record and record.changed_case_ids_json == [case["case_id"]]
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(
                sa.delete(WorkerTask).where(WorkerTask.task_id == "api-import-worker")
            )
            connection.execute(sa.delete(AiGenerateTask))
