"""Task deletion preserves formal assets and their documented provenance behavior."""

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
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
        version = seed_row(
            connection,
            AiGenerateStageVersion.__table__,
            {
                "task_id": task["task_id"],
                "attempt_id": attempt["id"],
            },
        )
        version_source = seed_row(
            connection,
            AiGenerateVersionImport.__table__,
            {
                "task_id": task["task_id"],
                "version_id": version["version_id"],
                "attempt_id": None,
            },
        )
        candidate_source = seed_row(
            connection,
            AiGenerateVersionImport.__table__,
            {
                "task_id": task["task_id"],
                "version_id": None,
                "attempt_id": attempt["id"],
            },
        )
        version_suite = seed_row(
            connection,
            FunctionTestSuite.__table__,
            {
                "effective_import_id": version_source["import_id"],
            },
        )
        candidate_suite = seed_row(
            connection,
            FunctionTestSuite.__table__,
            {
                "effective_import_id": candidate_source["import_id"],
            },
        )
        unrelated_suite = seed_row(
            connection,
            FunctionTestSuite.__table__,
            {
                "effective_import_id": "unrelated-source",
            },
        )
        case = seed_row(
            connection, FunctionTestCase.__table__, {"suite_id": version_suite["suite_id"]}
        )
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
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sql = []
    sa.event.listen(
        engine.sync_engine,
        "before_cursor_execute",
        lambda _c, _u, s, _p, _x, _m: sql.append(s.lower()),
    )
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            obj = await session.scalar(
                sa.select(AiGenerateTask).where(AiGenerateTask.task_id == task["task_id"])
            )
            await delete_owned_data(session, obj)
            await session.commit()
            for suite, expected in (
                (version_suite, version_source["import_id"]),
                (candidate_suite, None),
            ):
                target = await session.scalar(
                    sa.select(FunctionTestSuite).where(
                        FunctionTestSuite.suite_id == suite["suite_id"]
                    )
                )
                assert target.effective_import_id == expected and target.name == suite["name"]
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
            assert not any("ai_generate_task_runs" in statement for statement in sql)
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(sa.delete(WorkerTask).where(WorkerTask.task_id == "shared-queue"))
            # The generic fixture creates additional parents for foreign-key defaults.
            connection.execute(sa.delete(AiGenerationStage))
