"""Real DB/HTTP restore fences and bounded retention, including old-event replay."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.integration_bug_api import api as api
from support.integration_bug_api import claim, rows, submit
from support.integration_bug_api import integration as integration
from support.integration_bug_api import setup as setup
from support.integration_jobs import claim as claim_request
from support.integration_jobs import harness as harness
from support.integration_jobs import result as remote_result
from support.integration_jobs import submission

from testing_agent.core.config import IntegrationExecutionSettings, get_settings
from testing_agent.core.errors import AppError
from testing_agent.domain.integration_execution import digest
from testing_agent.models import Base
from testing_agent.models.bug_zentao_attachment import BugZentaoAttachment
from testing_agent.models.bug_zentao_push import BugZentaoPush
from testing_agent.models.integration_job import (
    IntegrationClaimReceipt,
    IntegrationJob,
    IntegrationJobStep,
    IntegrationRuntime,
)
from testing_agent.models.project import Project
from testing_agent.services.integration_maintenance import IntegrationHistoryMaintenance
from testing_agent.services.integration_runtime import key_digest
from testing_agent.services.storage_backup import validate_restore_execution

NOW = datetime(2026, 10, 7, tzinfo=UTC)


@pytest_asyncio.fixture
async def history():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        session.add(Project(project_id="p", user_id="u", name="History fixture"))
        await session.commit()
    yield sessions
    await engine.dispose()


async def old_job(session, key, *, state="succeeded", days=100, step_state=None):
    job = IntegrationJob(
        job_id=key,
        protocol_version=1,
        task_type="zentao_bug_sync",
        project_id="p",
        bug_id=key,
        actor_user_id="u",
        service_id="s",
        connection_id="c",
        target_key=digest("target"),
        runtime_generation="runtime-1",
        request_id=key,
        request_digest=digest(key),
        input_revision=digest("input"),
        target_revision=digest("target"),
        snapshot_json={"clientRequest": digest(key), "source": {"html": "<p>old content</p>"}},
        mapping_json={"remoteBugId": 50},
        status=state,
        finished_at=NOW - timedelta(days=days),
    )
    session.add(job)
    await session.flush()
    step = IntegrationJobStep(
        job_id=key,
        step_key="create_bug",
        kind="create_bug",
        status=step_state or state,
        input_json={"payload": {"steps": "<p>old content</p>"}},
        operation_id="op-" + key,
        prepare_request_id="prepare-" + key,
        intent_worker_id="worker-1",
        intent_generation=1,
        result_json={"remoteBugId": 50},
        receipts_json=[{"eventId": "event-1", "digest": digest("event"), "response": {"ok": True}}],
    )
    session.add(step)
    await session.flush()
    return job, step


async def compact(session, **settings):
    return await IntegrationHistoryMaintenance(
        session, IntegrationExecutionSettings(**settings), clock=lambda: NOW
    ).compact()


async def test_compaction_is_bounded_keeps_original_identity_and_reports_backlog(history):
    async with history() as session:
        jobs = [await old_job(session, str(n)) for n in range(3)]
        await session.commit()
        assert await compact(session, maintenance_batch_size=2) == {
            "compacted": 2,
            "backlog": 1,
            "prunedReceipts": 0,
        }
        assert [job.archived_at is not None for job, _ in jobs] == [True, True, False]
        assert jobs[0][0].snapshot_json == {"clientRequest": digest("0")}
        assert jobs[0][1].input_json == {}
        assert jobs[0][1].operation_id == "op-0"
        assert jobs[0][1].receipts_json[0]["response"] == {"ok": True}
        await session.commit()
        assert await compact(session) == {"compacted": 1, "backlog": 0, "prunedReceipts": 0}
        await session.commit()
        assert await compact(session) == {"compacted": 0, "backlog": 0, "prunedReceipts": 0}


@pytest.mark.parametrize("kind", ["push", "description", "fields", "attachment"])
async def test_current_domain_mapping_is_protected_without_starving_unreferenced_history(
    history, kind
):
    async with history() as session:
        job, step = await old_job(session, "protected")
        await old_job(session, "eligible")
        if kind == "attachment":
            session.add(
                BugZentaoAttachment(
                    bug_id=job.bug_id,
                    file_id="file",
                    sha256=digest("file"),
                    instance_url="https://zentao.example",
                    remote_bug_id=50,
                    operation_id=step.operation_id,
                    actor_user_id="u",
                    status="succeeded",
                )
            )
        else:
            session.add(
                BugZentaoPush(
                    bug_id=job.bug_id,
                    operation_id=step.operation_id if kind == "push" else "other",
                    actor_user_id="u",
                    service_id="s",
                    instance_url="https://zentao.example",
                    status="succeeded",
                    remote_bug_id=50,
                    target_json={},
                    payload_json={"_fieldUpdate": {"operationId": step.operation_id}}
                    if kind == "fields"
                    else {},
                    description_operation_id=step.operation_id if kind == "description" else "",
                )
            )
        await session.commit()
        assert await compact(session, maintenance_batch_size=1) == {
            "compacted": 1,
            "backlog": 0,
            "prunedReceipts": 0,
        }
        assert job.archived_at is None
        assert step.input_json["payload"]["steps"] == "<p>old content</p>"


@pytest.mark.parametrize(
    "state,step_state,recovery",
    [
        ("unknown", "unknown", False),
        ("running", "write_intent", False),
        ("failed", "write_intent", False),
        ("succeeded", "succeeded", True),
        ("quarantined", "pending", True),
    ],
)
async def test_unresolved_and_quarantined_evidence_is_never_compacted(
    history, state, step_state, recovery
):
    async with history() as session:
        job, step = await old_job(session, "protected", state=state, step_state=step_state)
        job.recovery_required = recovery
        await session.commit()
        assert await compact(session) == {"compacted": 0, "backlog": 0, "prunedReceipts": 0}
        assert job.archived_at is None
        assert step.input_json


async def test_success_and_known_failure_have_separate_retention_windows(history):
    async with history() as session:
        success, _ = await old_job(session, "success", days=40)
        failure, _ = await old_job(session, "failure", days=40, state="failed")
        await session.commit()
        assert (await compact(session))["compacted"] == 1
        assert success.archived_at is not None
        assert failure.archived_at is None
        assert (await compact(session, failed_retention_days=20))["compacted"] == 1


async def test_compacted_result_only_returns_original_receipt_never_reapplies(harness):
    sessions, service, clock, controls = harness
    async with sessions() as session:
        job = await service(session).submit(submission())
        await service(session).claim(claim_request())
        from support.integration_jobs import prepare

        permit = await service(session).prepare(job.job_id, "create_bug", prepare())
        body = remote_result(permit["operationId"])
        receipt = await service(session).result(job.job_id, "create_bug", body)
        job.archived_at = clock()
        await session.commit()
        assert await service(session).result(job.job_id, "create_bug", body) == receipt
        assert controls["applications"] == 1
        with pytest.raises(AppError, match="已清理"):
            await service(session).result(
                job.job_id,
                "create_bug",
                body.model_copy(update={"event_id": "new-event"}),
                evidence=True,
            )
        assert controls["applications"] == 1


def test_restored_database_blocks_even_legacy_routes_and_old_config(api, integration):
    submitted, _ = submit(api, integration)
    claimed = claim(api, integration)["job"]
    settings = api.app.dependency_overrides[get_settings]()
    restored = replace(
        settings,
        integration_worker_key="new-restored-key",
        integration_execution=IntegrationExecutionSettings(
            runtime_generation="restored-generation", accept_submissions=False, claim_enabled=False
        ),
    )

    async def quarantine():
        async with api.app.state.test_sessions() as session:
            job = await session.scalar(
                select(IntegrationJob).where(IntegrationJob.job_id == submitted["jobId"])
            )
            job.recovery_required, job.status, job.active_scope = True, "quarantined", None
            session.add(
                IntegrationRuntime(
                    id=1,
                    restore_id="restore",
                    runtime_generation="restored-generation",
                    worker_key_digest=key_digest("new-restored-key"),
                    blocked=True,
                )
            )
            await session.commit()

    asyncio.run(quarantine())
    old = api.post(
        "/internal/integration-worker/jobs/" + claimed["jobId"] + "/heartbeat",
        headers=integration["headers"],
        json={key: claimed[key] for key in ("workerId", "claimGeneration", "runtimeGeneration")},
    )
    assert old.status_code == 401
    api.app.dependency_overrides[get_settings] = lambda: restored
    response = api.post(
        integration["createUrl"], headers=integration["owner"], json={"requestId": "restore-new"}
    )
    assert response.status_code == 409
    legacy = api.post(
        f"/v1/bugs/{integration['bug']['bugId']}/zentao-push", headers=integration["owner"]
    )
    assert legacy.status_code == 405
    fresh = api.post(
        "/internal/integration-worker/jobs/claim",
        headers={"X-Worker-Token": "new-restored-key"},
        json={
            "workerId": "new-worker",
            "claimRequestId": "new-request",
            "protocolVersions": [1],
            "taskTypes": ["zentao_bug_sync"],
        },
    )
    assert fresh.status_code == 409
    status = api.get(
        f"/v1/bugs/{integration['bug']['bugId']}/zentao-push", headers=integration["owner"]
    )
    assert status.status_code == 200, status.text
    assert not status.json()["data"]["ready"]
    assert status.json()["data"]["latestJob"]["jobStatus"] == "quarantined"
    assert len(rows(api, IntegrationJob)) == 1
    assert integration["remote"].calls == []


@pytest.mark.parametrize("change", ["enabled", "submissions", "claims", "key", "generation"])
def test_restore_requires_rotated_credentials_generation_and_disabled_gates(change):
    execution = IntegrationExecutionSettings(
        runtime_generation="new", accept_submissions=False, claim_enabled=False
    )
    settings = replace(
        get_settings(), integration_worker_key="new-key", integration_execution=execution
    )
    manifest = {
        "integrationExecution": {
            "runtimeGeneration": "old",
            "workerKeyFingerprint": key_digest("old-key"),
        }
    }
    validate_restore_execution(settings, manifest)
    if change == "key":
        settings = replace(settings, integration_worker_key="old-key")
    else:
        fields = {
            "enabled": {"enabled": True},
            "submissions": {"accept_submissions": True},
            "claims": {"claim_enabled": True},
            "generation": {"runtime_generation": "old"},
        }
        settings = replace(settings, integration_execution=replace(execution, **fields[change]))
    with pytest.raises(ValueError):
        validate_restore_execution(settings, manifest)


async def add_receipt(session, key, *, days=0, job_id=None):
    session.add(
        IntegrationClaimReceipt(
            claim_key=key,
            request_id=key,
            request_digest=digest(key),
            job_id=job_id,
            response_json={"job": None},
            created_at=NOW - timedelta(days=days),
        )
    )
    await session.flush()


async def test_claim_receipts_pruned_by_window_or_archived_job(history):
    async with history() as session:
        await old_job(session, "old-job")
        await add_receipt(session, "fresh", days=0)
        await add_receipt(session, "stale", days=20)
        await add_receipt(session, "of-old-job", days=0, job_id="old-job")
        await session.commit()
        result = await compact(session)
        assert result == {
            "compacted": 1,
            "backlog": 0,
            "prunedReceipts": 2,
        }
        keys = set(await session.scalars(select(IntegrationClaimReceipt.claim_key)))
        assert keys == {"fresh"}
        # 窗口内的回执继续承担领取重放保护。
        again = await compact(session)
        assert again == {"compacted": 0, "backlog": 0, "prunedReceipts": 0}
        assert set(await session.scalars(select(IntegrationClaimReceipt.claim_key))) == {"fresh"}


async def test_claim_receipts_prune_is_bounded(history):
    async with history() as session:
        for index in range(3):
            await add_receipt(session, f"stale-{index}", days=20)
        await session.commit()
        result = await compact(session, maintenance_batch_size=2)
        assert result["prunedReceipts"] == 2
        result = await compact(session, maintenance_batch_size=2)
        assert result["prunedReceipts"] == 1
        assert await session.scalar(select(func.count()).select_from(IntegrationClaimReceipt)) == 0
