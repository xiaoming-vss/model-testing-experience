"""Real MySQL serialization of continuous independent generation attempts."""

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.standalone_execution import start_standalone_execution
from testing_agent.services.standalone_worker_transitions import StandaloneWorkerTransitions


async def test_parallel_continuous_dispatches_keep_distinct_stage_attempts(mysql):  # noqa: F811
    with mysql.begin() as connection:
        task_row = seed_row(
            connection,
            AiGenerateTask.__table__,
            {"task_type": "functional_case_generate", "sprint_id": "", "requirement_id": ""},
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        for number in (1, 2):
            async with sessions() as session:
                task = await session.scalar(
                    sa.select(AiGenerateTask)
                    .where(AiGenerateTask.task_id == task_row["task_id"])
                    .with_for_update()
                )
                await start_standalone_execution(
                    session,
                    task=task,
                    execution_id=f"continuous-{number}",
                    request_id=f"continuous-worker-{number}",
                    actor_id="user",
                    connection_id="llm",
                    source={"sourceContent": str(number)},
                    config={},
                    checkpoint_enabled=False,
                )
                await session.commit()

        async def advance(number):
            async with sessions() as session:
                task = await session.scalar(
                    sa.select(AiGenerateTask).where(AiGenerateTask.task_id == task_row["task_id"])
                )
                queue = await session.scalar(
                    sa.select(WorkerTask)
                    .where(WorkerTask.task_id == f"continuous-worker-{number}")
                    .with_for_update()
                )
                transitions = StandaloneWorkerTransitions(session)
                await transitions.claimed(task, queue)
                await transitions.started(task, queue)
                attempt = await transitions.advance(
                    task,
                    queue,
                    next_stage="case_names",
                    content=f'{{"source":{number}}}',
                    output_format="json",
                    next_config={"requirementAnalysis": {"source": number}},
                )
                await session.commit()
                return (
                    attempt.id,
                    attempt.execution_id,
                    attempt.attempt_no,
                    attempt.input_snapshot_json,
                )

        results = await asyncio.wait_for(asyncio.gather(advance(1), advance(2)), timeout=15)
        assert {item[1] for item in results} == {"continuous-1", "continuous-2"}
        assert {item[2] for item in results} == {1, 2}
        assert {item[3]["config"]["requirementAnalysis"]["source"] for item in results} == {1, 2}
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(
                sa.delete(WorkerTask).where(
                    WorkerTask.domain == "ai",
                    WorkerTask.task_id.in_(["continuous-worker-1", "continuous-worker-2"]),
                )
            )
            connection.execute(
                sa.delete(AiGenerateTask).where(AiGenerateTask.task_id == task_row["task_id"])
            )
