"""Shared preparation for integration jobs tests; no collected cases."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from testing_agent.core.errors import AppError, ErrForbidden
from testing_agent.domain.integration_execution import digest
from testing_agent.models.integration_job import (
    IntegrationClaimReceipt,
    IntegrationJob,
    IntegrationJobStep,
)
from testing_agent.repositories.integration_job import IntegrationJobRepository
from testing_agent.schemas.integration_job import (
    IntegrationClaimRequest,
    IntegrationPrepareRequest,
    IntegrationResultRequest,
    IntegrationSubmission,
    IntegrationWorkerIdentity,
)
from testing_agent.services.integration_job import IntegrationJobService

TABLES = [IntegrationJob.__table__, IntegrationJobStep.__table__, IntegrationClaimReceipt.__table__]


@dataclass
class Clock:
    now: datetime = datetime(2026, 10, 6, tzinfo=UTC)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


@pytest_asyncio.fixture
async def harness():
    engine = create_async_engine("sqlite+aiosqlite://")

    @event.listens_for(engine.sync_engine, "connect")
    def explicit_transactions(dbapi_connection, _):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine.sync_engine, "begin")
    def begin(connection):
        connection.exec_driver_sql("BEGIN")

    async with engine.begin() as connection:
        await connection.run_sync(lambda c: IntegrationJob.metadata.create_all(c, tables=TABLES))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    clock = Clock()
    controls = {"revoked": False, "applications": 0, "fail_apply": False}

    async def authorize(job):
        if controls["revoked"]:
            raise ErrForbidden()

    async def validate_prepare(job, step, body):
        if body.access_revision != digest("access"):
            raise AppError(409, "访问授权已变化", 409)

    async def apply_result(job, step, evidence):
        if controls["fail_apply"]:
            raise RuntimeError("domain transaction failed")
        controls["applications"] += 1
        job.mapping_json = {**job.mapping_json, **step.result_json}

    def service(session):
        return IntegrationJobService(
            IntegrationJobRepository(session),
            authorize=authorize,
            validate_prepare=validate_prepare,
            apply_result=apply_result,
            runtime_generation="runtime-1",
            clock=clock,
        )

    yield sessions, service, clock, controls
    await engine.dispose()


def submission(**overrides):
    payload = {
        "request_id": "request-1",
        "task_type": "zentao_bug_sync",
        "project_id": "p",
        "bug_id": "b",
        "actor_user_id": "u",
        "service_id": "s",
        "connection_id": "c",
        "target_key": digest("instance-1"),
        "input_revision": digest("source-1"),
        "target_revision": digest("target-1"),
        "snapshot": {"html": "<p>original</p>"},
        "steps": [
            {"step_key": "create_bug", "kind": "create_bug"},
            {
                "step_key": "update_description",
                "kind": "update_description",
                "dependencies": ["create_bug"],
            },
        ],
    }
    payload.update(overrides)
    return IntegrationSubmission(**payload)


def claim(worker="worker-1", request="claim-1", **overrides):
    payload = {
        "worker_id": worker,
        "claim_request_id": request,
        "protocol_versions": [1],
        "task_types": ["zentao_bug_sync", "zentao_bug_fields_update"],
    }
    payload.update(overrides)
    return IntegrationClaimRequest(**payload)


def identity(generation=1, **overrides):
    return IntegrationWorkerIdentity(
        **{
            "worker_id": "worker-1",
            "claim_generation": generation,
            "runtime_generation": "runtime-1",
            **overrides,
        }
    )


def prepare(generation=1, **overrides):
    return IntegrationPrepareRequest(
        **{
            **identity(generation).model_dump(),
            "prepare_request_id": "prepare-1",
            "input_revision": digest("source-1"),
            "target_revision": digest("target-1"),
            "access_revision": digest("access"),
            "input": {"title": "frozen title"},
            **overrides,
        }
    )


def result(operation, **overrides):
    return IntegrationResultRequest(
        **{
            **identity().model_dump(),
            "event_id": "event-1",
            "operation_id": operation,
            "status": "succeeded",
            "result": {"remote_bug_id": 42},
            **overrides,
        }
    )


async def started(harness, *, one_step=False):
    sessions, make_service, _, _ = harness
    async with sessions() as session:
        body = submission()
        if one_step:
            body = body.model_copy(update={"steps": body.steps[:1]})
        job = await make_service(session).submit(body)
        await session.commit()
        await make_service(session).claim(claim())
        await session.commit()
        return job.job_id
