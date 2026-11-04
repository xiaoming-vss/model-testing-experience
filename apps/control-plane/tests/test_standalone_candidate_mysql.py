"""MySQL serializes candidate editing and review without mixing executions."""

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.standalone_candidate import (
    review_standalone_candidate,
    save_standalone_draft,
)
from testing_agent.services.standalone_dispatch import enqueue_standalone_attempt
from testing_agent.services.standalone_execution import start_standalone_execution


async def test_parallel_edit_and_review_remain_execution_scoped(mysql):  # noqa: F811
    with mysql.begin() as connection:
        task_row = seed_row(
            connection,
            AiGenerateTask.__table__,
            {"task_type": "api_case_generate", "sprint_id": "", "requirement_id": ""},
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    originals = {}
    try:
        for number in (1, 2):
            async with sessions() as session:
                task = await session.scalar(
                    sa.select(AiGenerateTask)
                    .where(AiGenerateTask.task_id == task_row["task_id"])
                    .with_for_update()
                )
                execution, attempt, _ = await start_standalone_execution(
                    session,
                    task=task,
                    execution_id=f"run-{number}",
                    request_id=f"worker-{number}",
                    actor_id="user",
                    connection_id="llm",
                    source={},
                    config={},
                    checkpoint_enabled=False,
                )
                execution.workflow_status, execution.current_stage = "success", "completed"
                attempt.status, attempt.output_content, attempt.output_format = (
                    "success",
                    f"original-{number}",
                    "text",
                )
                queue = await session.scalar(
                    sa.select(WorkerTask).where(WorkerTask.task_id == f"worker-{number}")
                )
                queue.status = "success"
                originals[number] = attempt.id
                await session.commit()

        async def edit(number):
            async with sessions() as session:
                task = await session.scalar(
                    sa.select(AiGenerateTask).where(AiGenerateTask.task_id == task_row["task_id"])
                )
                result = await save_standalone_draft(
                    session,
                    task=task,
                    execution_id=f"run-{number}",
                    stage_name="generate",
                    expected_attempt_id=originals[number],
                    actor_id=f"editor-{number}",
                    content=f"edited-{number}",
                    output_format="text",
                )
                await session.commit()
                return result.id, result.attempt_no

        edits = await asyncio.wait_for(asyncio.gather(edit(1), edit(2)), timeout=15)
        assert {number for _, number in edits} == {3, 4}

        async def review(actor):
            async with sessions() as session:
                task = await session.scalar(
                    sa.select(AiGenerateTask).where(AiGenerateTask.task_id == task_row["task_id"])
                )
                try:
                    await review_standalone_candidate(
                        session,
                        task=task,
                        execution_id="run-1",
                        stage_name="generate",
                        expected_attempt_id=edits[0][0],
                        actor_id=actor,
                        approved=True,
                        comment=actor,
                    )
                    await session.commit()
                    return True
                except AppError:
                    await session.rollback()
                    return False

        reviewed = await asyncio.wait_for(
            asyncio.gather(review("reviewer-a"), review("reviewer-b")), timeout=15
        )
        assert sum(reviewed) == 1
        async with sessions() as session:
            first = await session.get(AiGenerationAttempt, edits[0][0])
            second = await session.get(AiGenerationAttempt, edits[1][0])
            assert first.review_status == "approved" and first.reviewer_user_id in {
                "reviewer-a",
                "reviewer-b",
            }
            assert second.review_status == "pending" and second.reviewer_user_id is None
            assert first.output_content == "edited-1" and second.output_content == "edited-2"
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


async def test_concurrent_retries_of_one_execution_enqueue_once(mysql):  # noqa: F811
    with mysql.begin() as connection:
        task_row = seed_row(
            connection,
            AiGenerateTask.__table__,
            {"task_type": "functional_case_generate", "sprint_id": "", "requirement_id": ""},
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            task = await session.scalar(
                sa.select(AiGenerateTask)
                .where(AiGenerateTask.task_id == task_row["task_id"])
                .with_for_update()
            )
            execution, first, _ = await start_standalone_execution(
                session,
                task=task,
                execution_id="retry-run",
                request_id="original-worker",
                actor_id="user",
                connection_id="llm",
                source={"sourceContent": "original"},
                config={},
                checkpoint_enabled=True,
            )
            first.status, first.error_message = "failed", "failure"
            execution.workflow_status = "failed"
            queue = await session.scalar(
                sa.select(WorkerTask).where(WorkerTask.task_id == "original-worker")
            )
            queue.status = "failed"
            attempt_id = first.id
            await session.commit()

        async def retry(number):
            async with sessions() as session:
                task = await session.scalar(
                    sa.select(AiGenerateTask).where(AiGenerateTask.task_id == task_row["task_id"])
                )
                try:
                    attempt, _ = await enqueue_standalone_attempt(
                        session,
                        task=task,
                        execution_id="retry-run",
                        request_id=f"retry-worker-{number}",
                        actor_id="user",
                        connection_id="llm",
                        stage_name="requirement_analysis",
                        operation="retry",
                        expected_attempt_id=attempt_id,
                    )
                    await session.commit()
                    return attempt.id
                except AppError:
                    await session.rollback()
                    return None

        results = await asyncio.wait_for(asyncio.gather(retry(1), retry(2)), timeout=15)
        assert sum(value is not None for value in results) == 1
        async with sessions() as session:
            attempts = (
                await session.scalars(
                    sa.select(AiGenerationAttempt).where(
                        AiGenerationAttempt.execution_id == "retry-run"
                    )
                )
            ).all()
            assert len(attempts) == 2
            assert sum(attempt.status == "pending" for attempt in attempts) == 1
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(
                sa.delete(WorkerTask).where(
                    WorkerTask.domain == "ai",
                    WorkerTask.task_id.in_(["original-worker", "retry-worker-1", "retry-worker-2"]),
                )
            )
            connection.execute(
                sa.delete(AiGenerateTask).where(AiGenerateTask.task_id == task_row["task_id"])
            )


async def test_parallel_retries_of_different_executions(mysql):  # noqa: F811
    with mysql.begin() as connection:
        task_row = seed_row(
            connection,
            AiGenerateTask.__table__,
            {"task_type": "functional_case_generate", "sprint_id": "", "requirement_id": ""},
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    originals = {}
    try:
        for number in (1, 2):
            async with sessions() as session:
                task = await session.scalar(
                    sa.select(AiGenerateTask)
                    .where(AiGenerateTask.task_id == task_row["task_id"])
                    .with_for_update()
                )
                execution, first, _ = await start_standalone_execution(
                    session,
                    task=task,
                    execution_id=f"parallel-run-{number}",
                    request_id=f"parallel-original-{number}",
                    actor_id="user",
                    connection_id="llm",
                    source={},
                    config={},
                    checkpoint_enabled=True,
                )
                execution.workflow_status, first.status = "failed", "failed"
                queue = await session.scalar(
                    sa.select(WorkerTask).where(WorkerTask.task_id == f"parallel-original-{number}")
                )
                queue.status = "failed"
                originals[number] = first.id
                await session.commit()

        async def retry(number):
            async with sessions() as session:
                task = await session.scalar(
                    sa.select(AiGenerateTask).where(AiGenerateTask.task_id == task_row["task_id"])
                )
                attempt, _ = await enqueue_standalone_attempt(
                    session,
                    task=task,
                    execution_id=f"parallel-run-{number}",
                    request_id=f"parallel-retry-{number}",
                    actor_id="user",
                    connection_id="llm",
                    stage_name="requirement_analysis",
                    operation="retry",
                    expected_attempt_id=originals[number],
                )
                await session.commit()
                return attempt.id

        results = await asyncio.wait_for(asyncio.gather(retry(1), retry(2)), timeout=15)
        assert len(set(results)) == 2
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(
                sa.delete(WorkerTask).where(
                    WorkerTask.domain == "ai",
                    WorkerTask.task_id.in_(
                        [f"parallel-{kind}-{n}" for kind in ("original", "retry") for n in (1, 2)]
                    ),
                )
            )
            connection.execute(
                sa.delete(AiGenerateTask).where(AiGenerateTask.task_id == task_row["task_id"])
            )


async def test_parallel_retries_for_different_tasks(mysql):  # noqa: F811
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
    originals = {}
    try:
        for number in (1, 2):
            async with sessions() as session:
                task = await session.scalar(
                    sa.select(AiGenerateTask)
                    .where(AiGenerateTask.task_id == rows[number - 1]["task_id"])
                    .with_for_update()
                )
                execution, attempt, _ = await start_standalone_execution(
                    session,
                    task=task,
                    execution_id=f"different-run-{number}",
                    request_id=f"different-original-{number}",
                    actor_id="user",
                    connection_id="llm",
                    source={},
                    config={},
                    checkpoint_enabled=True,
                )
                execution.workflow_status, attempt.status = "failed", "failed"
                queue = await session.scalar(
                    sa.select(WorkerTask).where(
                        WorkerTask.task_id == f"different-original-{number}"
                    )
                )
                queue.status = "failed"
                originals[number] = attempt.id
                await session.commit()

        async def retry(number):
            async with sessions() as session:
                task = await session.scalar(
                    sa.select(AiGenerateTask).where(
                        AiGenerateTask.task_id == rows[number - 1]["task_id"]
                    )
                )
                attempt, _ = await enqueue_standalone_attempt(
                    session,
                    task=task,
                    execution_id=f"different-run-{number}",
                    request_id=f"different-retry-{number}",
                    actor_id="user",
                    connection_id="llm",
                    stage_name="requirement_analysis",
                    operation="retry",
                    expected_attempt_id=originals[number],
                )
                await session.commit()
                return attempt.id

        results = await asyncio.wait_for(asyncio.gather(retry(1), retry(2)), timeout=15)
        assert len(set(results)) == 2
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(
                sa.delete(WorkerTask).where(
                    WorkerTask.domain == "ai",
                    WorkerTask.task_id.in_(
                        [f"different-{kind}-{n}" for kind in ("original", "retry") for n in (1, 2)]
                    ),
                )
            )
            connection.execute(
                sa.delete(AiGenerateTask).where(
                    AiGenerateTask.task_id.in_([row["task_id"] for row in rows])
                )
            )
