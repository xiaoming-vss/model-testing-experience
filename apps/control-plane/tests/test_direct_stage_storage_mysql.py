"""direct-stage concurrency against a disposable MySQL database."""

import asyncio
import os
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.initial_schema_migration import migration_config
from support.mysql_initialization import seed_row

from alembic import command
from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.services.stage_storage import DirectStageStorage


@pytest.fixture(scope="module", autouse=True)
def clean_disposable_schema():
    """This module creates its own schema; leave the database empty for the next module."""
    url = os.environ.get("CONTROL_PLANE_TEST_DATABASE_URL")
    if not url:
        yield
        return
    engine = sa.create_engine(url)
    assert engine.url.database and engine.url.database.endswith("_test")
    try:
        with engine.connect() as connection:
            assert sa.inspect(connection).get_table_names() == [], "Test database must be empty"
        yield
        with engine.begin() as connection:
            connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")
            for name in sa.inspect(connection).get_table_names():
                quoted = connection.dialect.identifier_preparer.quote(name)
                connection.exec_driver_sql(f"DROP TABLE {quoted}")
            connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS=1")
    finally:
        engine.dispose()


async def test_same_stage_concurrent_dispatch_is_serialized():
    url = os.environ.get("CONTROL_PLANE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("A disposable MySQL test database was not supplied")
    engine = sa.create_engine(url)
    assert engine.url.database and engine.url.database.endswith("_test")
    with engine.connect() as connection:
        assert sa.inspect(connection).get_table_names() == []
        command.upgrade(migration_config(connection), "head")
        connection.commit()
        task = seed_row(connection, AiGenerateTask.__table__)
        stage_id = str(uuid4())
        connection.execute(
            AiGenerationStage.__table__.insert().values(
                id=stage_id, task_id=task["task_id"], stage="case_names"
            )
        )
        connection.commit()
    async_engine = create_async_engine(engine.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    try:

        async def launch(worker_id):
            async with sessions() as session:
                try:
                    async with session.begin():
                        attempt = await DirectStageStorage(session).prepare(
                            stage_id, worker_task_id=worker_id, requested_by="u", input_snapshot={}
                        )
                    return attempt.id
                except AppError:
                    return None

        results = await asyncio.gather(launch("worker-1"), launch("worker-2"))
        assert sum(value is not None for value in results) == 1
        async with sessions() as session:
            stage = await session.get(AiGenerationStage, stage_id)
            assert stage is not None and stage.active_attempt_id == next(v for v in results if v)
    finally:
        await async_engine.dispose()
        engine.dispose()


async def test_different_stages_can_dispatch_at_the_same_time():
    url = os.environ.get("CONTROL_PLANE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("A disposable MySQL test database was not supplied")
    engine = sa.create_engine(url)
    assert engine.url.database and engine.url.database.endswith("_test")
    with engine.connect() as connection:
        task = seed_row(connection, AiGenerateTask.__table__)
        ids = [str(uuid4()), str(uuid4())]
        for stage_id, label in zip(ids, ("case_names", "detailed_cases"), strict=True):
            connection.execute(
                AiGenerationStage.__table__.insert().values(
                    id=stage_id, task_id=task["task_id"], stage=label
                )
            )
        connection.commit()
    async_engine = create_async_engine(engine.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    try:

        async def launch(stage_id):
            async with sessions() as session, session.begin():
                return await DirectStageStorage(session).prepare(
                    stage_id, worker_task_id=str(uuid4()), requested_by="u", input_snapshot={}
                )

        results = await asyncio.gather(*(launch(stage_id) for stage_id in ids))
        assert {attempt.stage_id for attempt in results} == set(ids)
    finally:
        await async_engine.dispose()
        engine.dispose()


async def test_idempotency_lookup_does_not_deadlock_with_worker_queue_lock():
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.services.stage_storage.dispatch import dispatch_stage_attempt

    url = os.environ.get("CONTROL_PLANE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("A disposable MySQL test database was not supplied")
    engine = sa.create_engine(url)
    assert engine.url.database and engine.url.database.endswith("_test")
    with engine.connect() as connection:
        task = seed_row(connection, AiGenerateTask.__table__)
        stage_id = str(uuid4())
        connection.execute(
            AiGenerationStage.__table__.insert().values(
                id=stage_id, task_id=task["task_id"], stage="case_names"
            )
        )
        connection.commit()
    async_engine = create_async_engine(engine.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    try:
        async with sessions() as session, session.begin():
            task_model = await session.get(AiGenerateTask, task["id"])
            await dispatch_stage_attempt(
                session,
                task=task_model,
                stage_id=stage_id,
                request_id="locked-worker",
                actor_id="u",
                input_snapshot={},
            )
        async with sessions() as worker_session, worker_session.begin():
            await worker_session.scalar(
                sa.select(WorkerTask).where(WorkerTask.task_id == "locked-worker").with_for_update()
            )

            async def retry():
                async with sessions() as session:
                    with pytest.raises(AppError):
                        async with session.begin():
                            task_model = await session.get(AiGenerateTask, task["id"])
                            await dispatch_stage_attempt(
                                session,
                                task=task_model,
                                stage_id=stage_id,
                                request_id="locked-worker",
                                actor_id="u",
                                input_snapshot={},
                            )

            await asyncio.wait_for(retry(), timeout=3)
            locked_stage = await asyncio.wait_for(
                worker_session.scalar(
                    sa.select(AiGenerationStage)
                    .where(AiGenerationStage.id == stage_id)
                    .with_for_update()
                ),
                timeout=3,
            )
            assert locked_stage is not None
    finally:
        await async_engine.dispose()
        engine.dispose()
