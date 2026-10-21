from dataclasses import replace

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from testing_agent.core.errors import AppError
from testing_agent.models.function_case_push import (
    FunctionCasePushOperation,
    FunctionCaseRemoteIdentity,
)
from testing_agent.repositories.function_case_push import FunctionCasePushRepository
from testing_agent.services.function_case_push_journal import CasePushJournal, CaseWriteIntent


@pytest_asyncio.fixture
async def sessions(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'journal.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: FunctionCaseRemoteIdentity.__table__.create(sync))
        await connection.run_sync(lambda sync: FunctionCasePushOperation.__table__.create(sync))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def intent(**changes):
    return replace(
        CaseWriteIntent(
            project_id="project",
            case_id="case",
            instance_key="a" * 64,
            actor="actor",
            request_id="request",
            target={"product": 1, "execution": 2, "story": 3},
            payload={"title": "同名用例", "steps": ["A"]},
        ),
        **changes,
    )


@pytest.mark.asyncio
async def test_lost_response_replays_receipt_without_another_write_permit(sessions):
    async with sessions() as session:
        journal = CasePushJournal(FunctionCasePushRepository(session))
        permit = await journal.reserve(intent())
        assert permit.allowed
        operation_id = permit.operation.operation_id
        # The journal itself does not commit the caller's transaction.
        async with sessions() as observer:
            assert await observer.scalar(select(FunctionCasePushOperation)) is None
        await session.commit()
    async with sessions() as session:
        journal = CasePushJournal(FunctionCasePushRepository(session))
        replay = await journal.reserve(intent())
        assert not replay.allowed
        assert replay.operation.operation_id == operation_id
        with pytest.raises(AppError, match="未决写入"):
            await journal.reserve(intent(request_id="another-request"))
        await session.rollback()
        await journal.record(operation_id, "unknown", error_code="remote_uncertain")
        await session.commit()
    async with sessions() as session:
        journal = CasePushJournal(FunctionCasePushRepository(session))
        with pytest.raises(AppError, match="未决写入"):
            await journal.reserve(intent(request_id="after-restart"))
        await session.rollback()
        await journal.record(operation_id, "succeeded", remote_case_id=71)
        await session.commit()
        replay = await journal.reserve(intent())
        assert not replay.allowed and replay.operation.result_json["remoteCaseId"] == 71
        updated = await journal.reserve(intent(request_id="update", remote_case_id=71))
        assert updated.allowed and updated.operation.action == "update"
        await session.rollback()


@pytest.mark.asyncio
async def test_same_title_different_cases_have_distinct_create_permits(sessions):
    async with sessions() as session:
        journal = CasePushJournal(FunctionCasePushRepository(session))
        first = await journal.reserve(intent())
        second = await journal.reserve(intent(case_id="other-case"))
        assert first.allowed and second.allowed
        assert first.operation.identity_id != second.operation.identity_id
        await journal.record(first.operation.operation_id, "succeeded", remote_case_id=71)
        await journal.record(second.operation.operation_id, "succeeded", remote_case_id=72)
        await session.commit()
        identities = (await session.scalars(select(FunctionCaseRemoteIdentity))).all()
        assert {row.remote_case_id for row in identities} == {71, 72}


@pytest.mark.asyncio
async def test_changed_request_and_conflicting_final_receipt_are_rejected(sessions):
    async with sessions() as session:
        journal = CasePushJournal(FunctionCasePushRepository(session))
        permit = await journal.reserve(intent())
        with pytest.raises(AppError, match="不同用例推送内容"):
            await journal.reserve(intent(payload={"title": "changed"}))
        await journal.record(permit.operation.operation_id, "succeeded", remote_case_id=71)
        await journal.record(permit.operation.operation_id, "succeeded", remote_case_id=71)
        with pytest.raises(AppError, match="不同的终态"):
            await journal.record(permit.operation.operation_id, "succeeded", remote_case_id=72)
        await session.commit()


@pytest.mark.asyncio
async def test_database_guards_remote_binding_and_preserves_referenced_evidence(sessions):
    async with sessions() as session:
        journal = CasePushJournal(FunctionCasePushRepository(session))
        permit = await journal.reserve(intent(remote_case_id=71))
        identity_id = permit.operation.identity_id
        await session.commit()
        with pytest.raises(IntegrityError):
            await journal.reserve(intent(case_id="other", remote_case_id=71))
        await session.rollback()
        identity = await session.get(FunctionCaseRemoteIdentity, identity_id)
        with pytest.raises(IntegrityError):
            await session.delete(identity)
            await session.flush()
        await session.rollback()


def test_migration_refuses_to_discard_existing_identity_evidence():
    import sqlalchemy as sa
    from support.initial_schema_migration import migration_config

    from alembic import command

    engine = sa.create_engine("sqlite://")
    with engine.connect() as connection:
        config = migration_config(connection)
        command.upgrade(config, "head")
        connection.execute(
            FunctionCaseRemoteIdentity.__table__.insert().values(
                project_id="deleted-project",
                case_id="deleted-case",
                instance_key="b" * 64,
                remote_case_id=123,
                target_json={"execution": 1},
                revision=1,
            )
        )
        connection.commit()
        with pytest.raises(RuntimeError, match="Preserve testcase identity"):
            command.downgrade(config, "20261020_0043")
        connection.rollback()
        assert connection.scalar(select(FunctionCaseRemoteIdentity.remote_case_id)) == 123
        assert "function_case_push_operations" in sa.inspect(connection).get_table_names()
    engine.dispose()


@pytest.mark.asyncio
async def test_frozen_intent_does_not_follow_caller_mutation_or_store_credentials(sessions):
    async with sessions() as session:
        journal = CasePushJournal(FunctionCasePushRepository(session))
        body = intent()
        permit = await journal.reserve(body)
        body.payload["steps"].append("changed-after-reservation")
        body.target["execution"] = 999
        assert permit.operation.payload_json["steps"] == ["A"]
        assert permit.operation.target_json["execution"] == 2
        await session.rollback()
        with pytest.raises(ValueError, match="access material"):
            await journal.reserve(intent(payload={"token": "must-not-persist"}))
        assert await session.scalar(select(FunctionCasePushOperation)) is None
