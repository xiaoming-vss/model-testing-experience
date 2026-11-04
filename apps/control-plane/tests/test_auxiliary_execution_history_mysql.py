"""Exercise unified auxiliary dispatch and history against MySQL."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.auxiliary_execution import dispatch_auxiliary_execution
from testing_agent.services.auxiliary_execution_delete import delete_auxiliary_execution
from testing_agent.services.auxiliary_execution_view import auxiliary_detail, auxiliary_history
from testing_agent.services.stage_storage.worker import StageWorkerTransitions


async def test_unified_auxiliary_history_on_mysql(mysql):  # noqa: F811
    with mysql.begin() as connection:
        task_row = seed_row(
            connection,
            AiGenerateTask.__table__,
            {"task_type": "test_order_graph", "sprint_id": "", "requirement_id": ""},
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            task = await session.scalar(
                select(AiGenerateTask)
                .where(AiGenerateTask.task_id == task_row["task_id"])
                .with_for_update()
            )
            for number in range(2):
                attempt, _ = await dispatch_auxiliary_execution(
                    session,
                    task=task,
                    actor_id="user",
                    request_id=f"worker-{number}",
                    execution_id=f"execution-{number}",
                    connection_id="connection",
                    source={"name": "frozen"},
                    config={"graphInput": {"cases": [number]}},
                )
                await StageWorkerTransitions(session).completed(
                    attempt.stage_id,
                    attempt.id,
                    attempt.worker_task_id,
                    content=f"result-{number}",
                    output_format="text",
                    output_context=None,
                )
                queue = await session.scalar(
                    select(WorkerTask).where(
                        WorkerTask.domain == "ai", WorkerTask.task_id == f"worker-{number}"
                    )
                )
                queue.status = "success"
                await session.commit()
            history = await auxiliary_history(session, task.task_id, 1, 1)
            detail = await auxiliary_detail(session, "execution-0")
            assert history["total"] == 2
            assert history["items"][0]["runId"] == "execution-1"
            assert history["statusCounts"] == {"success": 2}
            assert detail["resultYaml"] == "result-0"
            assert detail["configJson"]["graphInput"]["cases"] == [0]
            await delete_auxiliary_execution(
                session, task_id=task.task_id, execution_id="execution-1"
            )
            await session.commit()
            remaining = await auxiliary_history(session, task.task_id, 1, 20)
            assert remaining["total"] == 1
            assert remaining["latestRun"]["runId"] == "execution-0"
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(
                delete(WorkerTask).where(
                    WorkerTask.domain == "ai", WorkerTask.task_id.in_(["worker-0", "worker-1"])
                )
            )
            connection.execute(
                delete(AiGenerateTask).where(AiGenerateTask.task_id == task_row["task_id"])
            )
