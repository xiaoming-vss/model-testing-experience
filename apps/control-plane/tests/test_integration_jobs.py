"""Exercise the real queue/transaction implementation, with only authorization adapters replaced.

SQLite verifies persistence and protocol invariants, not MySQL row-lock concurrency.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from testing_agent.core.errors import AppError, ErrForbidden
from testing_agent.domain.integration_execution import aggregate, digest
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


@pytest.mark.parametrize(
    ("states", "canceled", "expected"),
    [
        (["succeeded", "pending"], False, "running"),
        (["succeeded", "write_intent"], False, "running"),
        (["succeeded", "unknown"], True, "unknown"),
        (["succeeded", "noop"], False, "succeeded"),
        (["succeeded", "failed"], False, "partial"),
        (["failed", "blocked"], False, "failed"),
        (["succeeded", "canceled"], True, "canceled"),
    ],
)
def test_aggregate(states, canceled, expected):
    assert aggregate(states, canceled=canceled) == expected


async def test_submit_idempotence_scope_conflict_and_changed_payload(harness):
    sessions, make_service, _, _ = harness
    async with sessions() as session:
        service = make_service(session)
        first = await service.submit(submission())
        await session.commit()
        assert (await service.submit(submission())).job_id == first.job_id
        with pytest.raises(AppError, match="不同集成操作"):
            await service.submit(submission(snapshot={"html": "new"}))
        with pytest.raises(AppError, match="活跃集成任务"):
            await service.submit(submission(request_id="other", actor_user_id="other-member"))
        await session.rollback()
        assert len((await session.scalars(select(IntegrationJob))).all()) == 1
        assert len((await session.scalars(select(IntegrationJobStep))).all()) == 2


async def test_rollback_drops_job_and_steps_together(harness):
    sessions, make_service, _, _ = harness
    async with sessions() as session:
        await make_service(session).submit(submission())
        await session.rollback()
        assert list((await session.scalars(select(IntegrationJob))).all()) == []
        assert list((await session.scalars(select(IntegrationJobStep))).all()) == []


async def test_empty_claim_receipt_and_old_claim_survive_reclaim(harness):
    sessions, make_service, clock, _ = harness
    async with sessions() as session:
        service = make_service(session)
        empty_request = claim(request="empty")
        assert await service.claim(empty_request) == {"job": None}
        await session.commit()
        job = await service.submit(submission())
        await session.commit()
        assert await service.claim(empty_request) == {"job": None}
        first = await service.claim(claim())
        await session.commit()
        assert first["job"]["jobId"] == job.job_id
        clock.advance(61)
        assert await service.expire() == 1
        await session.commit()
        second = await service.claim(claim(request="claim-2"))
        await session.commit()
        assert second["job"]["claimGeneration"] == 2
        assert await service.claim(claim()) == first
        with pytest.raises(AppError, match="领取身份"):
            await service.input(job.job_id, identity())
        assert (await service.input(job.job_id, identity(2)))["snapshot"][
            "html"
        ] == "<p>original</p>"


async def test_claim_capabilities_and_target_limit(harness):
    sessions, make_service, _, _ = harness
    async with sessions() as session:
        service = make_service(session)
        jobs = []
        for number, target in [(1, "same"), (2, "same"), (3, "other")]:
            jobs.append(
                await service.submit(
                    submission(
                        request_id=f"r{number}",
                        bug_id=f"b{number}",
                        target_key=digest(target),
                    )
                )
            )
        await session.commit()
        assert await service.claim(claim(request="unsupported", protocol_versions=[2])) == {
            "job": None
        }
        first = await service.claim(claim())
        await session.commit()
        second = await service.claim(claim(worker="worker-2"))
        await session.commit()
        assert first["job"]["jobId"] == jobs[0].job_id
        assert second["job"]["jobId"] == jobs[2].job_id
        assert jobs[1].status == "queued"


async def test_prepare_response_loss_never_grants_another_write(harness):
    job_id = await started(harness)
    sessions, make_service, clock, _ = harness
    async with sessions() as session:
        service = make_service(session)
        permit = await service.prepare(job_id, "create_bug", prepare())
        await session.commit()
        assert permit["writeAllowed"] is True
        duplicate = await service.prepare(job_id, "create_bug", prepare())
        assert duplicate["writeAllowed"] is False
        assert duplicate["operationId"] == permit["operationId"]
        clock.advance(61)
        await service.expire()
        await session.commit()
        job = await service.repository.get(job_id)
        assert job.status == "unknown"
        assert job.active_scope is None
        assert (await service.repository.steps(job_id))[0].status == "unknown"
        assert await service.claim(claim(request="after-intent")) == {"job": None}


async def test_result_retries_after_terminal_and_revocation_apply_once(harness):
    job_id = await started(harness, one_step=True)
    sessions, make_service, clock, controls = harness
    async with sessions() as session:
        service = make_service(session)
        permit = await service.prepare(job_id, "create_bug", prepare())
        await session.commit()
        event = result(permit["operationId"])
        response = await service.result(job_id, "create_bug", event)
        await session.commit()
        assert response["jobStatus"] == "succeeded"
        controls["revoked"] = True
        clock.advance(120)
        assert await service.result(job_id, "create_bug", event) == response
        assert controls["applications"] == 1
        with pytest.raises(AppError, match="不同内容"):
            await service.result(
                job_id, "create_bug", event.model_copy(update={"status": "failed"})
            )
        with pytest.raises(AppError, match="原写入意图"):
            await service.result(job_id, "create_bug", result("another-operation"))


async def test_late_evidence_after_revoke_and_result_transaction_failure(harness):
    job_id = await started(harness, one_step=True)
    sessions, make_service, clock, controls = harness
    async with sessions() as session:
        service = make_service(session)
        permit = await service.prepare(job_id, "create_bug", prepare())
        await session.commit()
        event = result(permit["operationId"])
        controls["fail_apply"] = True
        with pytest.raises(RuntimeError, match="domain transaction"):
            await service.result(job_id, "create_bug", event)
        await session.rollback()
        assert (await service.repository.steps(job_id))[0].status == "write_intent"
        clock.advance(61)
        await service.expire()
        await session.commit()
        controls["revoked"] = True
        controls["fail_apply"] = False
        with pytest.raises(AppError, match="租约"):
            await service.result(job_id, "create_bug", event)
        response = await service.result(job_id, "create_bug", event, evidence=True)
        await session.commit()
        assert response["jobStatus"] == "succeeded"
        assert await service.result(job_id, "create_bug", event, evidence=True) == response
        assert controls["applications"] == 1


async def test_revocation_keeps_uncertainty_and_cancellation(harness):
    job_id = await started(harness)
    sessions, make_service, _, _ = harness
    async with sessions() as session:
        service = make_service(session)
        permit = await service.prepare(job_id, "create_bug", prepare())
        await session.commit()
        assert await service.revoke(actor_user_id="unrelated") == 0
        assert await service.revoke(actor_user_id="u", project_id="p") == 1
        await session.commit()
        job = await service.repository.get(job_id)
        assert job.status == "unknown"
        assert job.active_scope is None
        response = await service.result(
            job_id, "create_bug", result(permit["operationId"]), evidence=True
        )
        await session.commit()
        assert response["jobStatus"] == "canceled"
        assert response["result"]["steps"]["update_description"] == "canceled"


async def test_revisions_dependencies_and_heartbeat(harness):
    job_id = await started(harness)
    sessions, make_service, clock, _ = harness
    async with sessions() as session:
        service = make_service(session)
        with pytest.raises(AppError, match="依赖步骤"):
            await service.prepare(job_id, "update_description", prepare())
        with pytest.raises(AppError, match="输入或目标"):
            await service.prepare(job_id, "create_bug", prepare(input_revision=digest("new")))
        with pytest.raises(AppError, match="访问授权"):
            await service.prepare(job_id, "create_bug", prepare(access_revision=digest("new")))
        clock.advance(45)
        assert (await service.heartbeat(job_id, identity()))["leaseSeconds"] == 60
        await session.commit()
        clock.advance(45)
        permit = await service.prepare(job_id, "create_bug", prepare())
        await session.commit()
        assert permit["writeAllowed"] is True
        assert permit["permitSeconds"] == 15


async def test_final_result_completes_job_without_completed_call_and_freezes_source(harness):
    job_id = await started(harness)
    sessions, make_service, _, _ = harness
    async with sessions() as session:
        service = make_service(session)
        first = await service.prepare(job_id, "create_bug", prepare())
        await session.commit()
        response = await service.result(job_id, "create_bug", result(first["operationId"]))
        await session.commit()
        assert response["jobStatus"] == "running"
        view = await service.input(job_id, identity())
        assert view["mapping"]["remoteBugId"] == 42
        assert view["snapshot"]["html"] == "<p>original</p>"
        second = await service.prepare(
            job_id, "update_description", prepare(prepare_request_id="p2")
        )
        await session.commit()
        response = await service.result(
            job_id,
            "update_description",
            result(
                second["operationId"],
                event_id="e2",
                result={"description_hash": digest("html")},
            ),
        )
        await session.commit()
        assert response["jobStatus"] == "succeeded"
        job = await service.repository.get(job_id)
        assert job.active_scope is None and job.active_target is None
        assert job.finished_at is not None


async def test_failed_dependencies_and_noop_have_explicit_results(harness):
    job_id = await started(harness)
    sessions, make_service, _, _ = harness
    async with sessions() as session:
        service = make_service(session)
        job = await service.repository.get(job_id, lock=True)
        await service.without_write(job, "create_bug", "failed", reason="remote_rejected")
        await session.commit()
        assert job.status == "failed"
        assert job.result_json["steps"]["update_description"] == "blocked"
        assert all(not step.operation_id for step in await service.repository.steps(job_id))


@pytest.mark.parametrize(
    "secret",
    [
        {"token": "secret"},
        {"mcp_token": "secret"},
        {"nested": [{"downloadUrl": "signed"}]},
        {"html": '<img src="https://s3/?X-Amz-Signature=secret">'},
    ],
)
async def test_history_rejects_access_material(harness, secret):
    sessions, make_service, _, _ = harness
    async with sessions() as session:
        with pytest.raises(ValueError, match="access material|signed URLs"):
            await make_service(session).submit(submission(snapshot=secret))
        assert list((await session.scalars(select(IntegrationJob))).all()) == []


async def test_runtime_generation_isolation(harness):
    job_id = await started(harness)
    sessions, make_service, _, _ = harness
    async with sessions() as session:
        service = make_service(session)
        service.runtime_generation = "runtime-restored"
        with pytest.raises(AppError, match="运行代次"):
            await service.input(job_id, identity())


async def test_future_capability_declarations_still_claim_the_supported_intersection(harness):
    sessions, make_service, _, _ = harness
    async with sessions() as session:
        service = make_service(session)
        job = await service.submit(submission())
        await session.commit()
        claimed = await service.claim(
            claim(
                protocol_versions=[1, 2], task_types=["zentao_bug_sync", "future_integration_type"]
            )
        )
        assert claimed["job"]["jobId"] == job.job_id
