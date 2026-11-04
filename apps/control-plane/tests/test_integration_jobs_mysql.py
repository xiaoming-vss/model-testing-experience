"""Opt-in isolated MySQL checks for actual queue locks and concurrent request receipts."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.integration_jobs import claim, submission
from support.mysql_initialization import mysql  # noqa: F401

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
async def queue(mysql):  # noqa: F811
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


async def test_authorization_reads_current_role_even_after_repeatable_read_snapshot(mysql):  # noqa: F811
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


async def test_readonly_recovery_rejects_current_demotion_despite_a_stale_snapshot(mysql):  # noqa: F811
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
