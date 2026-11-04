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
                id=stage_id, task_id=task["task_id"], stage="case_names", next_version_no=1
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
                    id=stage_id, task_id=task["task_id"], stage=label, next_version_no=1
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
                id=stage_id, task_id=task["task_id"], stage="case_names", next_version_no=1
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


async def test_dispatch_and_upstream_delete_serialize_on_version_lock():
    from datetime import UTC, datetime

    from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
    from testing_agent.services.stage_storage.dispatch import dispatch_stage_attempt
    from testing_agent.services.stage_storage.upstream import select_upstream_versions
    from testing_agent.services.stage_storage.version_delete import delete_stage_version

    url = os.environ.get("CONTROL_PLANE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("A disposable MySQL test database was not supplied")
    engine = sa.create_engine(url)
    assert engine.url.database and engine.url.database.endswith("_test")
    with engine.connect() as connection:
        task = seed_row(connection, AiGenerateTask.__table__)
        stage_id, version_id = str(uuid4()), str(uuid4())
        connection.execute(
            AiGenerationStage.__table__.insert().values(
                id=stage_id, task_id=task["task_id"], stage="case_names", next_version_no=1
            )
        )
        connection.execute(
            AiGenerateStageVersion.__table__.insert().values(
                version_id=version_id,
                task_id=task["task_id"],
                stage="requirement_analysis",
                version_no=1,
                attempt_id=str(uuid4()),
                artifact_content='{"analysis":1}',
                artifact_format="json",
                reviewer_user_id="u",
                review_comment="",
                created_at=datetime.now(UTC),
            )
        )
        connection.commit()
    async_engine = create_async_engine(engine.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    try:
        async with sessions() as dispatch, dispatch.begin():
            task_model = await dispatch.get(AiGenerateTask, task["id"])
            selected = await select_upstream_versions(
                dispatch, task_model, "function", "case_names", {}
            )
            assert selected["requirement_analysis"].version_id == version_id

            async def remove():
                async with sessions() as session:
                    with pytest.raises(AppError):
                        async with session.begin():
                            owner = await session.get(AiGenerateTask, task["id"])
                            await delete_stage_version(session, owner, version_id)

            deletion = asyncio.create_task(remove())
            await asyncio.sleep(0.1)
            await dispatch_stage_attempt(
                dispatch,
                task=task_model,
                stage_id=stage_id,
                request_id=str(uuid4()),
                actor_id="u",
                input_snapshot={
                    "versioning": {"upstreamVersions": {"requirement_analysis": version_id}}
                },
            )
        await asyncio.wait_for(deletion, timeout=5)
        async with sessions() as session:
            assert (
                await session.scalar(
                    sa.select(AiGenerateStageVersion.version_id).where(
                        AiGenerateStageVersion.version_id == version_id
                    )
                )
                == version_id
            )
    finally:
        await async_engine.dispose()
        engine.dispose()


async def test_deleted_version_cannot_be_selected_by_concurrent_dispatch():
    from datetime import UTC, datetime

    from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
    from testing_agent.services.stage_storage.upstream import select_upstream_versions
    from testing_agent.services.stage_storage.version_delete import delete_stage_version

    url = os.environ.get("CONTROL_PLANE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("A disposable MySQL test database was not supplied")
    engine = sa.create_engine(url)
    assert engine.url.database and engine.url.database.endswith("_test")
    with engine.connect() as connection:
        task = seed_row(connection, AiGenerateTask.__table__)
        version_id = str(uuid4())
        connection.execute(
            AiGenerateStageVersion.__table__.insert().values(
                version_id=version_id,
                task_id=task["task_id"],
                stage="requirement_analysis",
                version_no=1,
                attempt_id=str(uuid4()),
                artifact_content='{"analysis":1}',
                artifact_format="json",
                reviewer_user_id="u",
                review_comment="",
                created_at=datetime.now(UTC),
            )
        )
        connection.commit()
    async_engine = create_async_engine(engine.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    try:
        async with sessions() as deletion_session, deletion_session.begin():
            owner = await deletion_session.get(AiGenerateTask, task["id"])
            assert await delete_stage_version(deletion_session, owner, version_id) == 0

            async def select_version():
                async with sessions() as session:
                    with pytest.raises(AppError):
                        async with session.begin():
                            other = await session.get(AiGenerateTask, task["id"])
                            await select_upstream_versions(
                                session, other, "function", "case_names", {}
                            )

            selection = asyncio.create_task(select_version())
            await asyncio.sleep(0.1)
        await asyncio.wait_for(selection, timeout=5)
    finally:
        await async_engine.dispose()
        engine.dispose()


async def test_concurrent_whole_draft_saves_only_one_wins():
    """The second editor cannot overwrite a draft saved from the same old candidate."""
    url = os.environ.get("CONTROL_PLANE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("A disposable MySQL test database was not supplied")
    engine = sa.create_engine(url)
    assert engine.url.database and engine.url.database.endswith("_test")
    with engine.begin() as connection:
        task = seed_row(connection, AiGenerateTask.__table__)
        stage_id = str(uuid4())
        connection.execute(
            AiGenerationStage.__table__.insert().values(
                id=stage_id, task_id=task["task_id"], stage="case_names", next_version_no=1
            )
        )
    async_engine = create_async_engine(engine.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    try:
        async with sessions() as session, session.begin():
            storage = DirectStageStorage(session)
            candidate = await storage.prepare(
                stage_id, worker_task_id=str(uuid4()), requested_by="u", input_snapshot={}
            )
            await storage.publish(
                stage_id,
                attempt_id=candidate.id,
                worker_task_id=candidate.worker_task_id,
                content='{"original":true}',
                output_format="json",
                output_context=None,
            )
            candidate_id = candidate.id

        async def save(content):
            async with sessions() as session:
                try:
                    async with session.begin():
                        saved = await DirectStageStorage(session).save_draft(
                            stage_id,
                            expected_attempt_id=candidate_id,
                            requested_by="u",
                            content=content,
                            output_format="json",
                        )
                    return saved.id
                except AppError:
                    return None

        results = await asyncio.gather(save('{"editor":1}'), save('{"editor":2}'))
        assert sum(result is not None for result in results) == 1
        async with sessions() as session:
            stage = await session.get(AiGenerationStage, stage_id)
            assert stage.current_attempt_id == next(result for result in results if result)
    finally:
        await async_engine.dispose()
        engine.dispose()


async def test_concurrent_approval_creates_exactly_one_version():
    from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion

    url = os.environ.get("CONTROL_PLANE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("A disposable MySQL test database was not supplied")
    engine = sa.create_engine(url)
    assert engine.url.database and engine.url.database.endswith("_test")
    with engine.begin() as connection:
        task = seed_row(connection, AiGenerateTask.__table__)
        stage_id = str(uuid4())
        connection.execute(
            AiGenerationStage.__table__.insert().values(
                id=stage_id, task_id=task["task_id"], stage="case_names", next_version_no=1
            )
        )
    async_engine = create_async_engine(engine.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    try:
        async with sessions() as session, session.begin():
            storage = DirectStageStorage(session)
            attempt = await storage.prepare(
                stage_id, worker_task_id=str(uuid4()), requested_by="u", input_snapshot={}
            )
            await storage.publish(
                stage_id,
                attempt_id=attempt.id,
                worker_task_id=attempt.worker_task_id,
                content='{"point":true}',
                output_format="json",
                output_context=None,
            )
            attempt_id = attempt.id

        async def approve():
            async with sessions() as session:
                try:
                    async with session.begin():
                        version = await DirectStageStorage(session).approve(
                            stage_id,
                            expected_attempt_id=attempt_id,
                            reviewer_user_id="u",
                            comment="",
                        )
                    return version.version_id
                except AppError:
                    return None

        results = await asyncio.gather(approve(), approve())
        assert sum(result is not None for result in results) == 1
        async with sessions() as session:
            versions = (
                await session.scalars(
                    sa.select(AiGenerateStageVersion).where(
                        AiGenerateStageVersion.task_id == task["task_id"],
                        AiGenerateStageVersion.stage == "case_names",
                    )
                )
            ).all()
            assert [version.version_no for version in versions] == [1]
            assert (await session.get(AiGenerationStage, stage_id)).next_version_no == 2
    finally:
        await async_engine.dispose()
        engine.dispose()


async def test_rejection_does_not_block_on_worker_callback_lock():
    """A callback holding the queue lock cannot deadlock an attempted rejection."""
    from testing_agent.models.worker_task import WorkerTask

    url = os.environ.get("CONTROL_PLANE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("A disposable MySQL test database was not supplied")
    engine = sa.create_engine(url)
    assert engine.url.database and engine.url.database.endswith("_test")
    with engine.begin() as connection:
        task = seed_row(connection, AiGenerateTask.__table__)
        stage_id, worker_id = str(uuid4()), str(uuid4())
        connection.execute(
            AiGenerationStage.__table__.insert().values(
                id=stage_id, task_id=task["task_id"], stage="case_names", next_version_no=1
            )
        )
    async_engine = create_async_engine(engine.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    try:
        async with sessions() as session, session.begin():
            storage = DirectStageStorage(session)
            attempt = await storage.prepare(
                stage_id, worker_task_id=worker_id, requested_by="u", input_snapshot={}
            )
            session.add(
                WorkerTask(
                    domain="ai",
                    task_id=worker_id,
                    task_type="functional_case_generate",
                    run_id=attempt.id,
                    status="success",
                    error_message="discard",
                )
            )
            await storage.publish(
                stage_id,
                attempt_id=attempt.id,
                worker_task_id=worker_id,
                content='{"draft":true}',
                output_format="json",
                output_context=None,
            )
            attempt_id = attempt.id
        async with sessions() as callback, sessions() as reviewer:
            await callback.scalar(
                sa.select(WorkerTask).where(WorkerTask.task_id == worker_id).with_for_update()
            )
            with pytest.raises(AppError, match="阶段仍在处理回传"):
                await asyncio.wait_for(
                    DirectStageStorage(reviewer).reject(stage_id, expected_attempt_id=attempt_id),
                    timeout=2,
                )
            await reviewer.rollback()
            await callback.rollback()
            async with reviewer.begin():
                await DirectStageStorage(reviewer).reject(stage_id, expected_attempt_id=attempt_id)
            queue = await reviewer.scalar(
                sa.select(WorkerTask).where(WorkerTask.task_id == worker_id)
            )
            assert queue.error_message == ""
    finally:
        await async_engine.dispose()
        engine.dispose()
