"""Stage request replay across stale repeatable-read transactions on MySQL."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.core.errors import AppError, ErrForbidden
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.schemas.generation_chain import (
    GenerationChainReviewRequest,
    GenerationChainRevisionRequest,
    GenerationChainRunRequest,
)
from testing_agent.services.stage_storage import DirectStageStorage, commands, run_command


async def test_review_continuation_replays_from_stale_snapshot(mysql, monkeypatch):  # noqa: F811
    with mysql.begin() as connection:
        requirement = seed_row(connection, Requirement.__table__)
        sprint = (
            connection.execute(
                sa.select(Sprint).where(Sprint.sprint_id == requirement["sprint_id"])
            )
            .mappings()
            .one()
        )
        task = seed_row(
            connection,
            AiGenerateTask.__table__,
            {
                "task_type": "api_case_generate",
                "project_id": sprint["project_id"],
                "sprint_id": sprint["sprint_id"],
                "requirement_id": requirement["requirement_id"],
                "source_type": "openapi",
                "source_content": '{"openapi":"3.0","paths":{}}',
            },
        )
    monkeypatch.setattr(run_command, "require_personal_connection", AsyncMock())
    monkeypatch.setattr(commands, "validate_generation_artifact", AsyncMock())
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    worker_id = None

    def chain(session):
        async def get_task(*_args, **_kwargs):
            return await session.scalar(
                sa.select(AiGenerateTask)
                .where(AiGenerateTask.task_id == task["task_id"])
                .with_for_update()
                .execution_options(populate_existing=True)
            )

        return SimpleNamespace(
            tasks=AiGenerateTaskRepository(session),
            task=get_task,
            validate_stage=lambda *_: None,
            lock_upstream_versions=AsyncMock(),
            files=None,
        )

    try:
        async with sessions() as writer, sessions() as stale:
            writer_chain = chain(writer)
            task_row = await writer_chain.task()
            attempt = await run_command.start_stage(
                writer_chain,
                task_row,
                "api",
                "openapi_extract",
                GenerationChainRunRequest(connectionId="llm"),
                "actor",
            )
            worker_id = attempt.worker_task_id
            await DirectStageStorage(writer).publish(
                attempt.stage_id,
                attempt_id=attempt.id,
                worker_task_id=attempt.worker_task_id,
                content='{"paths":{}}',
                output_format="json",
                output_context=None,
            )
            await writer.commit()
            await stale.scalar(sa.select(sa.func.count()).select_from(WorkerTask))
            body = GenerationChainReviewRequest(
                action="approve",
                expectedAttemptId=attempt.id,
                continueAfter=True,
                connectionId="llm",
                requestId=uuid4(),
            )
            first, second = (
                commands.DirectStageCommands(writer_chain),
                commands.DirectStageCommands(chain(stale)),
            )
            first.run, second.run = (
                AsyncMock(return_value="continued"),
                AsyncMock(return_value="continued"),
            )
            assert (
                await first.review(
                    requirement["requirement_id"], "api", "openapi_extract", body, "actor"
                )
                == "continued"
            )
            assert (
                await second.review(
                    requirement["requirement_id"], "api", "openapi_extract", body, "actor"
                )
                == "continued"
            )
            first_request = first.run.await_args.args[3]
            replay_request = second.run.await_args.args[3]
            assert first_request.request_id == replay_request.request_id == body.request_id
            assert first_request.upstream_versions == replay_request.upstream_versions
            assert first_request.upstream_versions["openapi_extract"]
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            if worker_id:
                connection.execute(sa.delete(WorkerTask).where(WorkerTask.task_id == worker_id))
            connection.execute(
                sa.delete(AiGenerateTask).where(AiGenerateTask.task_id == task["task_id"])
            )


async def test_stage_run_and_revision_replay_ignore_stale_snapshot(mysql, monkeypatch):  # noqa: F811
    with mysql.begin() as connection:
        requirement = seed_row(connection, Requirement.__table__)
        sprint = (
            connection.execute(
                sa.select(Sprint).where(Sprint.sprint_id == requirement["sprint_id"])
            )
            .mappings()
            .one()
        )
        task = seed_row(
            connection,
            AiGenerateTask.__table__,
            {
                "task_type": "api_case_generate",
                "project_id": sprint["project_id"],
                "sprint_id": sprint["sprint_id"],
                "requirement_id": requirement["requirement_id"],
                "source_type": "openapi",
                "source_content": '{"openapi":"3.0","paths":{}}',
            },
        )
    auth = AsyncMock()
    monkeypatch.setattr(run_command, "require_personal_connection", auth)
    monkeypatch.setattr(commands, "require_personal_connection", auth)
    monkeypatch.setattr(commands, "build_chain_view", AsyncMock(return_value="view"))
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    statements = []
    sa.event.listen(
        engine.sync_engine,
        "before_cursor_execute",
        lambda _c, _u, s, _p, _x, _m: statements.append(s.lower()),
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    run_id, revision_id = str(uuid4()), str(uuid4())

    async def locked_task(session):
        return await session.scalar(
            sa.select(AiGenerateTask)
            .where(AiGenerateTask.task_id == task["task_id"])
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def chain(session):
        async def get_task(*_args, **_kwargs):
            return await locked_task(session)

        return SimpleNamespace(
            tasks=AiGenerateTaskRepository(session),
            task=get_task,
            validate_stage=lambda *_: None,
            lock_upstream_versions=AsyncMock(),
            files=None,
        )

    run_body = GenerationChainRunRequest(connectionId="llm", requestId=run_id)
    revision_body = GenerationChainRevisionRequest(
        connectionId="llm", instruction="补充", requestId=revision_id
    )
    try:
        async with sessions() as stale, sessions() as writer:
            await stale.scalar(sa.select(sa.func.count()).select_from(WorkerTask))
            task_row = await locked_task(writer)
            initial = await run_command.start_stage(
                chain(writer), task_row, "api", "openapi_extract", run_body, "actor"
            )
            attempt_id = initial.id
            await writer.commit()
            stale_task = await locked_task(stale)
            replay = await run_command.start_stage(
                chain(stale), stale_task, "api", "openapi_extract", run_body, "actor"
            )
            assert replay.id == attempt_id
            with pytest.raises(AppError):
                await run_command.start_stage(
                    chain(stale),
                    stale_task,
                    "api",
                    "openapi_extract",
                    run_body.model_copy(update={"instruction": "changed"}),
                    "actor",
                )
            await stale.rollback()

            await DirectStageStorage(writer).publish(
                initial.stage_id,
                attempt_id=attempt_id,
                worker_task_id=run_id,
                content='{"paths":{}}',
                output_format="json",
                output_context=None,
            )
            await writer.commit()
            await stale.scalar(sa.select(sa.func.count()).select_from(WorkerTask))
            first = commands.DirectStageCommands(chain(writer))
            second = commands.DirectStageCommands(chain(stale))
            assert (
                await first.revise(
                    requirement["requirement_id"], "api", "openapi_extract", revision_body, "actor"
                )
                == "view"
            )
            assert (
                await second.revise(
                    requirement["requirement_id"], "api", "openapi_extract", revision_body, "actor"
                )
                == "view"
            )
            assert (
                await stale.scalar(
                    sa.select(sa.func.count())
                    .select_from(AiGenerationAttempt)
                    .where(AiGenerationAttempt.worker_task_id == revision_id)
                )
                == 1
            )
            with pytest.raises(AppError):
                await second.revise(
                    requirement["requirement_id"],
                    "api",
                    "openapi_extract",
                    revision_body.model_copy(update={"instruction": "changed"}),
                    "actor",
                )
            await stale.rollback()
            auth.side_effect = ErrForbidden()
            with pytest.raises(AppError) as revoked:
                await second.revise(
                    requirement["requirement_id"], "api", "openapi_extract", revision_body, "actor"
                )
            assert revoked.value.http_code == 403
            await stale.rollback()
            auth.side_effect = None
            revised = await writer.scalar(
                sa.select(AiGenerationAttempt).where(
                    AiGenerationAttempt.worker_task_id == revision_id
                )
            )
            storage = DirectStageStorage(writer)
            await storage.publish(
                revised.stage_id,
                attempt_id=revised.id,
                worker_task_id=revision_id,
                content='{"paths":{}}',
                output_format="json",
                output_context=None,
            )
            await storage.reject(revised.stage_id, expected_attempt_id=revised.id)
            await writer.commit()
            await writer.refresh(revised)
            assert set(revised.input_snapshot_json) == {"requestSignature"}
            assert (
                await second.revise(
                    requirement["requirement_id"], "api", "openapi_extract", revision_body, "actor"
                )
                == "view"
            )
            assert not any("ai_generate_task_runs" in sql for sql in statements)
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(
                sa.delete(WorkerTask).where(WorkerTask.task_id.in_([run_id, revision_id]))
            )
            connection.execute(
                sa.delete(AiGenerateTask).where(AiGenerateTask.task_id == task["task_id"])
            )
            connection.execute(sa.delete(AiGenerationStage))


async def test_different_generation_tasks_start_in_parallel(mysql, monkeypatch):  # noqa: F811
    with mysql.begin() as connection:
        requirement = seed_row(connection, Requirement.__table__)
        sprint = (
            connection.execute(
                sa.select(Sprint).where(Sprint.sprint_id == requirement["sprint_id"])
            )
            .mappings()
            .one()
        )
        tasks = [
            seed_row(
                connection,
                AiGenerateTask.__table__,
                {
                    "task_type": "api_case_generate",
                    "project_id": sprint["project_id"],
                    "sprint_id": sprint["sprint_id"],
                    "requirement_id": requirement["requirement_id"],
                    "source_type": "openapi",
                    "source_content": '{"openapi":"3.0","paths":{}}',
                },
            )
            for _ in range(2)
        ]
    monkeypatch.setattr(run_command, "require_personal_connection", AsyncMock())
    original_stages = run_command._stages
    arrived = 0
    ready = asyncio.Event()

    async def simultaneous(*args, **kwargs):
        nonlocal arrived
        arrived += 1
        if arrived == 2:
            ready.set()
        await asyncio.wait_for(ready.wait(), timeout=5)
        return await original_stages(*args, **kwargs)

    monkeypatch.setattr(run_command, "_stages", simultaneous)
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    request_ids = [str(uuid4()), str(uuid4())]

    async def start(task, request_id):
        async with sessions() as session:
            row = await session.scalar(
                sa.select(AiGenerateTask)
                .where(AiGenerateTask.task_id == task["task_id"])
                .with_for_update()
            )
            chain = SimpleNamespace(tasks=AiGenerateTaskRepository(session))
            result = await run_command.start_stage(
                chain,
                row,
                "api",
                "openapi_extract",
                GenerationChainRunRequest(connectionId="llm", requestId=request_id),
                "actor",
            )
            await session.commit()
            return result.id

    try:
        outcomes = await asyncio.wait_for(
            asyncio.gather(
                *(start(task, identity) for task, identity in zip(tasks, request_ids, strict=True)),
                return_exceptions=True,
            ),
            timeout=15,
        )
        assert not [item for item in outcomes if isinstance(item, BaseException)], outcomes
        assert len(set(outcomes)) == 2
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(sa.delete(WorkerTask).where(WorkerTask.task_id.in_(request_ids)))
            connection.execute(
                sa.delete(AiGenerateTask).where(
                    AiGenerateTask.task_id.in_([t["task_id"] for t in tasks])
                )
            )
            connection.execute(sa.delete(AiGenerationStage))
