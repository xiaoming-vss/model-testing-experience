"""Opt-in isolated MySQL checks for actual queue locks and concurrent request receipts."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.integration_jobs import claim, submission
from support.mysql_initialization import mysql as mysql

from testing_agent.domain.integration_execution import digest
from testing_agent.models.integration_job import (
    IntegrationClaimReceipt,
    IntegrationJob,
    IntegrationJobStep,
    IntegrationWorkerPresence,
)
from testing_agent.repositories.integration_job import IntegrationJobRepository
from testing_agent.repositories.integration_observation import IntegrationObservationRepository
from testing_agent.services.integration_job import IntegrationJobService
from testing_agent.services.integration_transaction import local_transaction


@pytest_asyncio.fixture
async def queue(mysql):
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    prefix = uuid4().hex

    async def authorize(job):
        pass

    async def validate(job, step, body):
        pass

    async def apply_result(job, step, evidence):
        pass

    def service(session):
        return IntegrationJobService(
            IntegrationJobRepository(session),
            authorize=authorize,
            validate_prepare=validate,
            apply_result=apply_result,
            runtime_generation="mysql-test",
        )

    def body(number=1, target=None):
        return submission(
            request_id=f"{prefix}-{number}",
            bug_id=f"{prefix}-{number}",
            actor_user_id=prefix,
            target_key=digest(target or f"{prefix}-{number}"),
        )

    try:
        yield sessions, service, body, prefix
    finally:
        async with sessions() as session:
            job_ids = select(IntegrationJob.job_id).where(IntegrationJob.actor_user_id == prefix)
            # 回执不再携带 worker_id，库是本模块专用的可丢弃库，直接清空。
            await session.execute(delete(IntegrationClaimReceipt))
            await session.execute(
                delete(IntegrationJobStep).where(IntegrationJobStep.job_id.in_(job_ids))
            )
            await session.execute(
                delete(IntegrationJob).where(IntegrationJob.actor_user_id == prefix)
            )
            await session.execute(
                delete(IntegrationWorkerPresence).where(
                    IntegrationWorkerPresence.worker_id.like(prefix + "%")
                )
            )
            await session.commit()
        await engine.dispose()


async def test_worker_contact_is_concurrent_idempotent_and_capabilities_match_on_mysql(queue):
    sessions, service, body, prefix = queue
    request = claim(worker=prefix + "-worker")

    class Registration:
        def __init__(self, session):
            self.session = session

        @local_transaction
        async def run(self):
            await IntegrationObservationRepository(self.session).contact(
                request, "mysql-test", datetime.now(UTC)
            )
            await self.session.commit()

    async with sessions() as first, sessions() as second:
        await asyncio.gather(Registration(first).run(), Registration(second).run())
    async with sessions() as session:
        workers = (
            await session.scalars(
                select(IntegrationWorkerPresence).where(
                    IntegrationWorkerPresence.worker_id == request.worker_id
                )
            )
        ).all()
        assert len(workers) == 1 and workers[0].protocol_versions == [1]
        job = await service(session).submit(body())
        job.created_at = datetime.now(UTC) - timedelta(days=40)
        await session.commit()
        repository = IntegrationObservationRepository(session)
        assert await repository.availability(job, "mysql-test", datetime.now(UTC), 120) == "waiting"
        future = claim(worker=request.worker_id, protocol_versions=[2])
        await repository.contact(future, "mysql-test", datetime.now(UTC))
        await session.commit()
        assert (
            await repository.availability(job, "mysql-test", datetime.now(UTC), 120)
            == "worker_incompatible"
        )
        await service(session).claim(claim(worker=request.worker_id))
        await session.commit()
        await session.refresh(job)
        assert job.queue_wait_ms > 2_147_483_647
        report = await repository.aggregate(datetime.now(UTC), 24, job.project_id, 10)
        assert report["queue"][0] == 1 and int(report["queue"][1]) > 2_147_483_647


async def test_claim_skips_only_the_locked_job(queue):
    sessions, service, body, prefix = queue
    async with sessions() as session:
        jobs = [await service(session).submit(body(n)) for n in (1, 2)]
        await session.commit()
    async with sessions() as first, sessions() as second:
        a = await service(first).claim(claim(worker=prefix + "-a"))
        b = await asyncio.wait_for(service(second).claim(claim(worker=prefix + "-b")), timeout=5)
        assert {a["job"]["jobId"], b["job"]["jobId"]} == {job.job_id for job in jobs}
        await first.rollback()
        await second.rollback()


async def test_concurrent_same_request_has_one_job_and_receipt(queue):
    sessions, service, body, prefix = queue

    async def submit():
        async with sessions() as session:
            job = await service(session).submit(body())
            await session.commit()
            return job.job_id

    identifiers = await asyncio.wait_for(asyncio.gather(submit(), submit()), timeout=10)
    assert identifiers[0] == identifiers[1]

    async def take():
        async with sessions() as session:
            receipt = await service(session).claim(claim(worker=prefix + "-same"))
            await session.commit()
            return receipt

    a, b = await asyncio.wait_for(asyncio.gather(take(), take()), timeout=10)
    assert a == b
    assert a["job"]["jobId"] == identifiers[0]


async def test_target_execution_limit_is_shared_by_worker_replicas(queue):
    sessions, service, body, prefix = queue
    async with sessions() as session:
        jobs = [
            await service(session).submit(body(1, "same")),
            await service(session).submit(body(2, "same")),
            await service(session).submit(body(3, "other")),
        ]
        await session.commit()
    async with sessions() as first:
        a = await service(first).claim(claim(worker=prefix + "-a"))
        await first.commit()
    async with sessions() as second:
        b = await service(second).claim(claim(worker=prefix + "-b"))
        await second.commit()
    assert a["job"]["jobId"] == jobs[0].job_id
    assert b["job"]["jobId"] == jobs[2].job_id


async def test_rollback_has_no_job_steps_or_claim_residue(queue):
    sessions, service, body, prefix = queue
    async with sessions() as session:
        job = await service(session).submit(body())
        job_id = job.job_id
        await session.rollback()
    async with sessions() as session:
        assert await service(session).repository.get(job_id) is None
        response = await service(session).claim(claim(worker=prefix + "-a"))
        assert response == {"job": None}
        await session.rollback()
    async with sessions() as session:
        key = digest([prefix + "-a", "claim-1"])
        assert await service(session).repository.claim_receipt(key) is None


async def test_migration_preserves_unresolved_write_evidence(mysql):
    from sqlalchemy.orm import Session
    from support.initial_schema_migration import migration_config

    from alembic import command

    prefix = uuid4().hex
    with Session(mysql) as session:
        job = IntegrationJob(
            job_id=prefix,
            protocol_version=1,
            task_type="zentao_bug_sync",
            project_id="p",
            bug_id="b",
            actor_user_id=prefix,
            service_id="s",
            connection_id="c",
            target_key=digest("t"),
            runtime_generation="r",
            request_id=prefix,
            request_digest=digest("r"),
            input_revision=digest("i"),
            target_revision=digest("t"),
            snapshot_json={},
            status="unknown",
            created_at=datetime.now(UTC),
        )
        session.add(job)
        session.commit()
    try:
        import pytest

        with mysql.connect() as connection:
            with pytest.raises(RuntimeError, match="禁止删除执行证据"):
                command.downgrade(migration_config(connection), "20261006_0029")
            connection.rollback()
    finally:
        with mysql.begin() as connection:
            connection.execute(delete(IntegrationJob).where(IntegrationJob.job_id == prefix))


async def test_retention_query_and_compaction_on_mysql(queue):
    from datetime import timedelta

    from testing_agent.core.config import IntegrationExecutionSettings
    from testing_agent.services.integration_maintenance import IntegrationHistoryMaintenance

    sessions, service, body, prefix = queue
    async with sessions() as session:
        job = await service(session).submit(body())
        await service(session).cancel(job, "canceled")
        job.finished_at = datetime.now(UTC) - timedelta(days=100)
        steps = await service(session).repository.steps(job.job_id)
        await session.commit()
        result = await IntegrationHistoryMaintenance(
            session, IntegrationExecutionSettings()
        ).compact()
        assert result == {"compacted": 1, "backlog": 0, "prunedReceipts": 0}
        assert job.archived_at is not None
        assert job.snapshot_json == {}
        assert all(step.input_json == {} for step in steps)
        await session.commit()


def test_migration_keeps_durable_restore_fence(mysql):
    import pytest
    from sqlalchemy.orm import Session
    from support.initial_schema_migration import migration_config

    from alembic import command
    from testing_agent.models.integration_job import IntegrationRuntime

    # Exercise the guard at its own revision. Starting at head first removes newer
    # account tables via nontransactional DDL before reaching this expected rejection.
    with mysql.connect() as connection:
        command.downgrade(migration_config(connection), "20261010_0039")
        connection.commit()
    with Session(mysql) as session:
        session.add(
            IntegrationRuntime(
                id=1,
                restore_id="owned-test-restore",
                runtime_generation="new",
                worker_key_digest=digest("fixture-key"),
                blocked=True,
            )
        )
        session.commit()
    try:
        with mysql.connect() as connection:
            with pytest.raises(RuntimeError, match="隔离标记"):
                command.downgrade(migration_config(connection), "20261006_0030")
            connection.rollback()
    finally:
        with mysql.begin() as connection:
            connection.execute(delete(IntegrationRuntime).where(IntegrationRuntime.id == 1))
        # MySQL DDL before the guarded revision is not rolled back by connection.rollback().
        # Restore the shared module database before later tests use the current ORM.
        with mysql.connect() as connection:
            command.upgrade(migration_config(connection), "head")
            connection.commit()


def test_restore_review_scope_constraint_and_migration_evidence_guard(mysql):
    import pytest
    from sqlalchemy import inspect
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session
    from support.initial_schema_migration import migration_config

    from alembic import command
    from testing_agent.models.integration_job import IntegrationRestoreReview

    with mysql.connect() as connection:
        command.downgrade(migration_config(connection), "20261010_0039")
        connection.commit()
    prefix = uuid4().hex

    def row(identifier):
        return IntegrationRestoreReview(
            review_id=identifier,
            restore_id=prefix,
            scope_type="bug",
            scope_id="bug",
            project_id="deleted-project",
            actor_user_id=None,
            decision="isolated",
            state_digest=digest("scope"),
            reviewed_at=datetime.now(UTC),
        )

    with Session(mysql) as session:
        session.add(row(prefix))
        session.commit()
        session.add(row(prefix + "-duplicate"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    try:
        with mysql.connect() as connection:
            before = inspect(connection).get_table_names()
            with pytest.raises(RuntimeError, match="核对证据"):
                command.downgrade(migration_config(connection), "20261007_0031")
            connection.rollback()
            assert inspect(connection).get_table_names() == before
    finally:
        with mysql.begin() as connection:
            connection.execute(
                delete(IntegrationRestoreReview).where(
                    IntegrationRestoreReview.restore_id == prefix
                )
            )
        with mysql.connect() as connection:
            command.upgrade(migration_config(connection), "head")
            connection.commit()


async def test_authorization_reads_current_role_even_after_repeatable_read_snapshot(mysql):
    import pytest
    from sqlalchemy import update

    from testing_agent.core.errors import AppError
    from testing_agent.models.bug import Bug
    from testing_agent.models.integration_connection import IntegrationConnection
    from testing_agent.models.project import Project
    from testing_agent.models.project_member import ProjectMember
    from testing_agent.models.shared_service import ServiceAuthorization, SharedService
    from testing_agent.models.user import User
    from testing_agent.services.integration_authorization import IntegrationAuthorization
    from testing_agent.services.integration_credentials import IntegrationCredentialCipher

    prefix = uuid4().hex
    owner, member = prefix + "-owner", prefix + "-member"
    cipher = IntegrationCredentialCipher("isolated-authorization-mysql")
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            session.add_all(
                [User(user_id=owner, nickname=owner), User(user_id=member, nickname=member)]
            )
            session.add(Project(project_id=prefix, user_id=owner, name=prefix))
            await session.flush()
            session.add(ProjectMember(project_id=prefix, user_id=member, role="member"))
            session.add(
                Bug(bug_id=prefix, project_id=prefix, title="role fence", found_sprint_id="s")
            )
            session.add(
                SharedService(
                    service_id=prefix,
                    project_id=prefix,
                    provider="mcp",
                    template_id="zentao",
                    name=prefix,
                    base_url="http://mcp.test/mcp",
                )
            )
            session.add(
                IntegrationConnection(
                    connection_id=prefix,
                    user_id=member,
                    project_id=prefix,
                    provider="mcp",
                    name=prefix,
                    secret_json={"token": cipher.encrypt("test-token")},
                )
            )
            await session.flush()
            session.add(
                ServiceAuthorization(service_id=prefix, user_id=member, connection_id=prefix)
            )
            await session.commit()
        async with sessions() as first, sessions() as second:
            query = select(ProjectMember.role).where(ProjectMember.project_id == prefix)
            assert await first.scalar(query) == "member"
            await second.execute(
                update(ProjectMember)
                .where(ProjectMember.project_id == prefix)
                .values(role="viewer")
            )
            await second.commit()
            assert (
                await first.scalar(query) == "member"
            )  # Existing RR snapshot is deliberately stale.
            task = IntegrationJob(
                project_id=prefix,
                bug_id=prefix,
                actor_user_id=member,
                service_id=prefix,
                connection_id=prefix,
            )
            with pytest.raises(AppError) as error:
                await IntegrationAuthorization(first, cipher).access(task)
            assert error.value.http_code == 403
            await first.rollback()
    finally:
        async with sessions() as session:
            for model, predicate in (
                (ServiceAuthorization, ServiceAuthorization.service_id == prefix),
                (IntegrationConnection, IntegrationConnection.connection_id == prefix),
                (SharedService, SharedService.service_id == prefix),
                (Bug, Bug.bug_id == prefix),
                (ProjectMember, ProjectMember.project_id == prefix),
                (Project, Project.project_id == prefix),
                (User, User.user_id.in_([owner, member])),
            ):
                await session.execute(delete(model).where(predicate))
            await session.commit()
        await engine.dispose()


async def test_readonly_recovery_rejects_current_demotion_despite_a_stale_snapshot(mysql):
    import pytest
    from sqlalchemy import update

    from testing_agent.core.errors import AppError
    from testing_agent.models.bug import Bug
    from testing_agent.models.project import Project
    from testing_agent.models.project_member import ProjectMember
    from testing_agent.models.user import User
    from testing_agent.services.integration_recovery import lock_recovery

    prefix = uuid4().hex
    owner, member = prefix + "-owner", prefix + "-member"
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            session.add_all(
                [User(user_id=owner, nickname=owner), User(user_id=member, nickname=member)]
            )
            session.add(Project(project_id=prefix, user_id=owner, name=prefix))
            await session.flush()
            session.add(ProjectMember(project_id=prefix, user_id=member, role="member"))
            session.add(
                Bug(
                    bug_id=prefix,
                    project_id=prefix,
                    title="recovery role fence",
                    found_sprint_id="s",
                )
            )
            await session.commit()
        async with sessions() as stale, sessions() as current:
            query = select(ProjectMember.role).where(ProjectMember.project_id == prefix)
            assert await stale.scalar(query) == "member"
            await current.execute(
                update(ProjectMember)
                .where(ProjectMember.project_id == prefix)
                .values(role="viewer")
            )
            await current.commit()
            assert await stale.scalar(query) == "member"
            with pytest.raises(AppError) as error:
                await lock_recovery(stale, prefix, member)
            assert error.value.http_code == 403
            await stale.rollback()
    finally:
        async with sessions() as session:
            for model, predicate in (
                (Bug, Bug.bug_id == prefix),
                (ProjectMember, ProjectMember.project_id == prefix),
                (Project, Project.project_id == prefix),
                (User, User.user_id.in_([owner, member])),
            ):
                await session.execute(delete(model).where(predicate))
            await session.commit()
        await engine.dispose()
