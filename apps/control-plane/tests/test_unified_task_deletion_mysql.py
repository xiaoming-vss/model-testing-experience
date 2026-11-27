"""Task deletion preserves formal assets and their documented provenance behavior."""

import sqlalchemy as sa
from support.mysql_initialization import (  # noqa: F401
    async_sessions,
    capture_statements,
    mysql,
    seed_row,
)

from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_import import AiGenerateImport, AiGenerateImportRequest
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.deletion import delete_owned_data


async def test_delete_task_preserves_formal_assets_and_provenance_semantics(mysql):  # noqa: F811
    with mysql.begin() as connection:
        task = seed_row(
            connection, AiGenerateTask.__table__, {"task_type": "functional_case_generate"}
        )
        stage = seed_row(connection, AiGenerationStage.__table__, {"task_id": task["task_id"]})
        execution = seed_row(connection, AiExecution.__table__, {"task_id": task["task_id"]})
        attempt = seed_row(
            connection,
            AiGenerationAttempt.__table__,
            {
                "stage_id": stage["id"],
                "execution_id": execution["execution_id"],
                "attempt_no": 1,
            },
        )
        request = seed_row(connection, AiGenerateImportRequest.__table__)
        source = seed_row(
            connection,
            AiGenerateImport.__table__,
            {
                "request_id": request["request_id"],
                "source_kind": "current",
                "task_id": task["task_id"],
                "source_attempt_id": attempt["id"],
                "changed_case_ids_json": [],
                "target_case_count": 1,
            },
        )
        suite = seed_row(
            connection,
            FunctionTestSuite.__table__,
            {
                "effective_import_id": source["import_id"],
            },
        )
        unrelated_suite = seed_row(
            connection,
            FunctionTestSuite.__table__,
            {
                "effective_import_id": "unrelated-source",
            },
        )
        case = seed_row(connection, FunctionTestCase.__table__, {"suite_id": suite["suite_id"]})
        for domain in ("ai", "api"):
            seed_row(
                connection,
                WorkerTask.__table__,
                {
                    "domain": domain,
                    "task_id": "shared-queue",
                    "task_type": "functional_case_generate",
                    "run_id": attempt["id"],
                    "status": "success",
                },
            )
    engine, sessions = async_sessions(mysql)
    statements = capture_statements(engine)
    try:
        async with sessions() as session:
            obj = await session.scalar(
                sa.select(AiGenerateTask).where(AiGenerateTask.task_id == task["task_id"])
            )
            await delete_owned_data(session, obj)
            await session.commit()
            target = await session.scalar(
                sa.select(FunctionTestSuite).where(FunctionTestSuite.suite_id == suite["suite_id"])
            )
            assert target.effective_import_id == source["import_id"]
            assert target.name == suite["name"]
            assert await session.get(AiGenerateImport, source["import_id"]) is not None
            target = await session.scalar(
                sa.select(FunctionTestSuite).where(
                    FunctionTestSuite.suite_id == unrelated_suite["suite_id"]
                )
            )
            assert target.effective_import_id == "unrelated-source"
            asset = await session.scalar(
                sa.select(FunctionTestCase).where(FunctionTestCase.case_id == case["case_id"])
            )
            assert asset.title == case["title"]
            assert (
                await session.scalar(
                    sa.select(WorkerTask).where(
                        WorkerTask.domain == "ai", WorkerTask.task_id == "shared-queue"
                    )
                )
                is None
            )
            assert (
                await session.scalar(
                    sa.select(WorkerTask).where(
                        WorkerTask.domain == "api", WorkerTask.task_id == "shared-queue"
                    )
                )
                is not None
            )
            assert not any("ai_generate_task_runs" in statement for statement in statements)
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(sa.delete(WorkerTask).where(WorkerTask.task_id == "shared-queue"))
            # The generic fixture creates additional parents for foreign-key defaults.
            connection.execute(sa.delete(AiGenerationStage))
