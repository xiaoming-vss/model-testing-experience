"""Real SQL observations and lease commands; only domain authorization is substituted."""

from dataclasses import replace
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from test_integration_jobs import claim, identity, prepare, result, started, submission
from test_integration_jobs import harness as harness

from testing_agent.core.config import Settings
from testing_agent.domain.integration_execution import digest, utc
from testing_agent.models.integration_job import (
    IntegrationJobStep,
    IntegrationRestoreReview,
    IntegrationRuntime,
    IntegrationWorkerPresence,
)
from testing_agent.repositories.integration_observation import IntegrationObservationRepository
from testing_agent.services.integration_observation import IntegrationObservation


@pytest_asyncio.fixture
async def observed(harness):
    sessions, commands, clock, controls = harness
    async with sessions.kw["bind"].begin() as connection:
        await connection.run_sync(lambda c: IntegrationRuntime.__table__.create(c))
        await connection.run_sync(lambda c: IntegrationWorkerPresence.__table__.create(c))
        await connection.run_sync(lambda c: IntegrationRestoreReview.__table__.create(c))
    settings = Settings.from_mapping(
        {
            "security": {"integration_worker": {"key": "dedicated-fixture-key"}},
            "integration_execution": {
                "enabled": True,
                "all_projects": True,
                "runtime_generation": "runtime-1",
                "worker_presence_ttl_seconds": 10,
            },
        }
    )
    return harness, settings


async def test_queue_explanations_follow_authenticated_capability_ttl_generation_and_switch(
    observed,
):
    (sessions, commands, clock, _), settings = observed
    async with sessions() as session:
        job = await commands(session).submit(submission())
        job.created_at = clock()
        await session.commit()
        observation = IntegrationObservation(session, settings, clock=clock)
        assert (await observation.explain(job))["queueReason"] == "worker_offline"
        await observation.repository.contact(claim(protocol_versions=[2]), "runtime-1", clock())
        await session.commit()
        assert (await observation.explain(job))["queueReason"] == "worker_incompatible"
        await observation.repository.contact(
            claim(task_types=["future_type"]), "runtime-1", clock()
        )
        await session.commit()
        assert (await observation.explain(job))["queueReason"] == "worker_incompatible"
        await observation.repository.contact(claim(), "runtime-1", clock())
        await session.commit()
        assert (await observation.explain(job))["queueReason"] == "waiting"
        clock.advance(11)
        assert (await observation.explain(job))["queueReason"] == "worker_offline"
        await observation.repository.heartbeat(identity(), clock())
        await session.commit()
        assert (await observation.explain(job))["queueReason"] == "waiting"
        await observation.repository.contact(claim(), "old-generation", clock())
        await session.commit()
        assert (await observation.explain(job))["queueReason"] == "worker_offline"
        paused = replace(
            settings,
            integration_execution=replace(settings.integration_execution, claim_enabled=False),
        )
        assert (await IntegrationObservation(session, paused, clock=clock).explain(job))[
            "queueReason"
        ] == "paused"
        session.add(
            IntegrationRuntime(
                id=1,
                restore_id="restore",
                runtime_generation="runtime-1",
                worker_key_digest=digest("key"),
                blocked=False,
            )
        )
        session.add(
            IntegrationRestoreReview(
                review_id="isolation",
                restore_id="restore",
                scope_type="bug",
                scope_id="b",
                project_id="p",
                decision="isolated",
                state_digest=digest("state"),
                facts_json={},
                reviewed_at=clock(),
            )
        )
        await session.commit()
        assert (await observation.explain(job))["queueReason"] == "paused"
        job.runtime_generation = "old-generation"
        assert (await observation.explain(job))["queueReason"] == "runtime_changed"


async def test_unknown_duration_and_lease_observations_survive_recovery_without_double_count(
    observed,
):
    (sessions, commands, clock, _), settings = observed
    async with sessions() as session:
        job = await commands(session).submit(
            submission(steps=[{"step_key": "create_bug", "kind": "create_bug"}])
        )
        job.created_at = clock()
        await session.commit()
        clock.advance(5)
        service = commands(session)
        await service.claim(claim())
        permit = await service.prepare(job.job_id, "create_bug", prepare())
        await session.commit()
        unknown = result(
            permit["operationId"],
            status="unknown",
            remote_duration_ms=180000,
            result={"errorCode": "lease_lost"},
        )
        await service.result(job.job_id, "create_bug", unknown)
        await session.commit()
        step = await session.scalar(select(IntegrationJobStep))
        original_unknown = step.unknown_at
        clock.advance(5)
        event = result(permit["operationId"], event_id="recovered", remote_duration_ms=99)
        await service.result(job.job_id, "create_bug", event, evidence=True)
        await session.commit()
        await service.result(job.job_id, "create_bug", event, evidence=True)
        await session.commit()
        assert step.unknown_at == original_unknown and step.remote_duration_ms == 180000
        assert job.queue_wait_ms == 5000 and job.status == "succeeded"
        report = await IntegrationObservation(session, settings, clock=clock).snapshot(
            project_id="p"
        )
        assert report["operationCounts"]["unknownOperations"] == 1
        assert report["operationCounts"]["leaseLostOperations"] == 1
        assert report["services"][0]["durationSamples"] == 1
        assert report["services"][0]["averageRemoteMs"] == 180000
        assert report["queue"]["firstClaimSamples"] == 1
        other = await IntegrationObservation(session, settings, clock=clock).snapshot(
            project_id="other"
        )
        assert other["services"] == [] and not other["liveJobsByStatus"]
        assert other["queue"]["averageWaitMs"] is None


async def test_result_without_duration_keeps_legacy_digest_and_metrics_roll_back_with_receipt(
    observed,
):
    (sessions, commands, clock, controls), settings = observed
    job_id = await started(observed[0], one_step=True)
    async with sessions() as session:
        service = commands(session)
        permit = await service.prepare(job_id, "create_bug", prepare())
        await session.commit()
        body = result(permit["operationId"])
        controls["fail_apply"] = True
        with pytest.raises(RuntimeError):
            await service.result(
                job_id, "create_bug", body.model_copy(update={"remote_duration_ms": 1200})
            )
        await session.rollback()
        step = await session.scalar(select(IntegrationJobStep))
        assert step.remote_duration_ms is None and step.remote_recorded_at is None
        controls["fail_apply"] = False
        response = await service.result(job_id, "create_bug", body)
        await session.commit()
        legacy = body.model_dump(mode="json", by_alias=True)
        legacy.pop("remoteDurationMs")
        assert step.receipts_json[-1]["digest"] == digest(legacy)
        assert await service.result(job_id, "create_bug", body) == response


async def test_stale_presence_pruning_is_bounded_and_cannot_remove_fresh_contact(observed):
    (sessions, _, clock, _), settings = observed
    async with sessions() as session:
        repository = IntegrationObservationRepository(session)
        for worker in ("old-1", "old-2"):
            await repository.contact(claim(worker=worker), "runtime-1", clock() - timedelta(days=8))
        await repository.contact(claim(worker="fresh"), "runtime-1", clock())
        await session.commit()
        assert await repository.prune(clock(), 1) == 1
        await session.commit()
        assert len((await session.scalars(select(IntegrationWorkerPresence))).all()) == 2
        assert await repository.prune(clock(), 100) == 1
        await session.commit()
        row = await session.scalar(select(IntegrationWorkerPresence))
        assert row.worker_id == "fresh" and utc(row.last_seen_at) == clock()


@pytest.mark.parametrize("value", [-1, True, 1.5, 86_400_001])
def test_duration_is_bounded_strict_integer(value):
    with pytest.raises(ValueError):
        result("operation", remote_duration_ms=value)


@pytest.mark.parametrize("value", [True, -1, 0, "1"])
def test_capability_versions_require_positive_integers(value):
    with pytest.raises(ValueError):
        claim(protocol_versions=[value])
