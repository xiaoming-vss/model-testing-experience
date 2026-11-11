"""Independent runs of one task may coexist without sharing stage state."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.standalone_execution import start_standalone_execution


async def test_task_delete_sees_active_execution_after_stale_snapshot(mysql):  # noqa: F811
    from testing_agent.core.errors import AppError
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.services.ai_task_commands import GenerationTaskCommands

    with mysql.begin() as connection:
        task_row = seed_row(
            connection,
            AiGenerateTask.__table__,
            {"task_type": "functional_case_generate", "sprint_id": "", "requirement_id": ""},
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as stale, sessions() as writer:
            task = await stale.scalar(
                sa.select(AiGenerateTask).where(AiGenerateTask.task_id == task_row["task_id"])
            )
            current = await writer.scalar(
                sa.select(AiGenerateTask)
                .where(AiGenerateTask.task_id == task_row["task_id"])
                .with_for_update()
            )
            await start_standalone_execution(
                writer,
                task=current,
                execution_id="delete-race-execution",
                request_id="delete-race-worker",
                actor_id="user",
                connection_id="llm",
                source={},
                config={},
                checkpoint_enabled=False,
            )
            await writer.commit()
            access = SimpleNamespace(
                owned_task=AsyncMock(return_value=task), validate_task_scope=AsyncMock()
            )
            deletion = AsyncMock()
            service = GenerationTaskCommands(
                AiGenerateTaskRepository(stale), access, deletion=deletion
            )
            with pytest.raises(AppError):
                await service.delete("function", task_row["task_id"], "user")
            deletion.delete.assert_not_awaited()
            await stale.rollback()
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(
                sa.delete(WorkerTask).where(WorkerTask.task_id == "delete-race-worker")
            )
            connection.execute(
                sa.delete(AiGenerateTask).where(AiGenerateTask.task_id == task_row["task_id"])
            )


async def test_parallel_independent_runs_keep_separate_attempts(mysql):  # noqa: F811
    with mysql.begin() as connection:
        task_row = seed_row(
            connection,
            AiGenerateTask.__table__,
            {"task_type": "functional_case_generate", "sprint_id": "", "requirement_id": ""},
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def start(number):
        async with sessions() as session:
            task = await session.scalar(
                sa.select(AiGenerateTask)
                .where(AiGenerateTask.task_id == task_row["task_id"])
                .with_for_update()
            )
            execution, attempt, _ = await start_standalone_execution(
                session,
                task=task,
                execution_id=f"execution-{number}",
                request_id=f"worker-{number}",
                actor_id="user",
                connection_id="llm",
                source={"sourceContent": f"input-{number}"},
                config={"number": number},
                checkpoint_enabled=True,
            )
            await session.commit()
            return execution.execution_id, attempt.id

    try:
        results = await asyncio.wait_for(asyncio.gather(start(1), start(2)), timeout=15)
        assert {row[0] for row in results} == {"execution-1", "execution-2"}
        async with sessions() as session:
            stages = list(
                (
                    await session.scalars(
                        sa.select(AiGenerationStage).where(
                            AiGenerationStage.task_id == task_row["task_id"]
                        )
                    )
                ).all()
            )
            attempts = list(
                (
                    await session.scalars(
                        sa.select(AiGenerationAttempt)
                        .where(AiGenerationAttempt.stage_id == stages[0].id)
                        .order_by(AiGenerationAttempt.attempt_no)
                    )
                ).all()
            )
            assert len(stages) == 1 and stages[0].active_attempt_id is None
            assert [attempt.attempt_no for attempt in attempts] == [1, 2]
            assert {attempt.execution_id for attempt in attempts} == {"execution-1", "execution-2"}
            assert {
                attempt.input_snapshot_json["source"]["sourceContent"] for attempt in attempts
            } == {"input-1", "input-2"}
            assert (
                len(
                    (
                        await session.scalars(
                            sa.select(AiExecution).where(AiExecution.task_id == task_row["task_id"])
                        )
                    ).all()
                )
                == 2
            )
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(
                sa.delete(WorkerTask).where(
                    WorkerTask.domain == "ai", WorkerTask.task_id.in_(["worker-1", "worker-2"])
                )
            )
            connection.execute(
                sa.delete(AiGenerateTask).where(AiGenerateTask.task_id == task_row["task_id"])
            )


async def test_start_replay_observes_commit_after_old_snapshot(mysql):  # noqa: F811
    with mysql.begin() as connection:
        task_row = seed_row(
            connection,
            AiGenerateTask.__table__,
            {"task_type": "functional_case_generate", "sprint_id": "", "requirement_id": ""},
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as first, sessions() as retry:
            # Establish the request's RR snapshot before the winner commits.
            await retry.scalar(sa.select(AiGenerateTask).where(AiGenerateTask.id == task_row["id"]))
            first_task = await first.scalar(
                sa.select(AiGenerateTask)
                .where(AiGenerateTask.task_id == task_row["task_id"])
                .with_for_update()
            )
            await start_standalone_execution(
                first,
                task=first_task,
                execution_id="winner",
                request_id="same-request",
                actor_id="user",
                connection_id="llm",
                source={},
                config={},
                checkpoint_enabled=True,
            )
            await first.commit()
            retry_task = await retry.scalar(
                sa.select(AiGenerateTask)
                .where(AiGenerateTask.task_id == task_row["task_id"])
                .with_for_update()
            )
            execution, _, replayed = await start_standalone_execution(
                retry,
                task=retry_task,
                execution_id="retry",
                request_id="same-request",
                actor_id="user",
                connection_id="llm",
                source={},
                config={},
                checkpoint_enabled=True,
            )
            assert replayed and execution.execution_id == "winner"
            await retry.rollback()
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(
                sa.delete(WorkerTask).where(
                    WorkerTask.domain == "ai", WorkerTask.task_id == "same-request"
                )
            )
            connection.execute(
                sa.delete(AiGenerateTask).where(AiGenerateTask.task_id == task_row["task_id"])
            )


async def test_different_tasks_start_concurrently_and_request_id_cannot_cross_tasks(mysql):  # noqa: F811
    from testing_agent.core.errors import AppError

    with mysql.begin() as connection:
        rows = [
            seed_row(
                connection,
                AiGenerateTask.__table__,
                {"task_type": "functional_case_generate", "sprint_id": "", "requirement_id": ""},
            )
            for _ in range(2)
        ]
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def start(number, request_id):
        async with sessions() as session:
            task = await session.scalar(
                sa.select(AiGenerateTask)
                .where(AiGenerateTask.task_id == rows[number - 1]["task_id"])
                .with_for_update()
            )
            try:
                result, _, _ = await start_standalone_execution(
                    session,
                    task=task,
                    execution_id=f"cross-{request_id}-{number}",
                    request_id=request_id,
                    actor_id="user",
                    connection_id="llm",
                    source={"number": number},
                    config={},
                    checkpoint_enabled=True,
                )
                await session.commit()
                return result.execution_id
            except AppError:
                await session.rollback()
                return None

    try:
        parallel = await asyncio.wait_for(
            asyncio.gather(start(1, "cross-a"), start(2, "cross-b")), timeout=15
        )
        assert all(parallel)
        collision = await asyncio.wait_for(
            asyncio.gather(start(1, "cross-shared"), start(2, "cross-shared")), timeout=15
        )
        assert sum(value is not None for value in collision) == 1
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(
                sa.delete(WorkerTask).where(
                    WorkerTask.domain == "ai",
                    WorkerTask.task_id.in_(["cross-a", "cross-b", "cross-shared"]),
                )
            )
            connection.execute(
                sa.delete(AiGenerateTask).where(
                    AiGenerateTask.task_id.in_([row["task_id"] for row in rows])
                )
            )
