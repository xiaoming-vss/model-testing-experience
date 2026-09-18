"""Queue dispatch, lease and compatibility tests using real SQLAlchemy transactions."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Boolean, Integer, select
from test_ai_execution_storage import (
    AsyncSessionAdapter,
    create_run,
    enqueue,
    event,
    graph,
)
from test_ai_execution_storage import db as db
from test_mysql_initialization import mysql as mysql

from testing_agent.core.errors import ErrBadRequest, ErrForbidden
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.api_collection_run import ApiCollectionRun, ApiCollectionRunItem
from testing_agent.models.ui_test_case_run import UiTestCaseRun
from testing_agent.models.ui_test_suite_run import UiTestSuiteRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.worker_task import WorkerTaskRepository
from testing_agent.schemas.workers import WorkerClaimRequest, WorkerTaskEventRequest
from testing_agent.services.worker_context import hydrate
from testing_agent.services.worker_task import WorkerTaskService, ensure_worker_match


def row(model, **values):
    for col in model.__table__.columns:
        if col.name in values or col.nullable or col.default is not None or col.primary_key:
            continue
        values[col.name] = (
            False
            if isinstance(col.type, Boolean)
            else (0 if isinstance(col.type, Integer) else "test")
        )
    return model(**values)


def add_business_tables(db):
    from test_api_run_scope import seed

    from testing_agent.models.api_case import ApiCase

    seed(db)
    db.add(row(ApiCase, case_id="case", collection_id="collection"))
    db.flush()

    for model in (
        ApiCaseRun,
        ApiCollectionRun,
        ApiCollectionRunItem,
        UiTestCaseRun,
        UiTestSuiteRun,
    ):
        model.__table__.create(db.get_bind(), checkfirst=True)


@pytest.mark.parametrize(
    "domain,kind,model,key,expected",
    [
        (
            "api",
            "api_case_debug",
            ApiCaseRun,
            "run_id",
            {"caseId": "case", "collectionId": "collection"},
        ),
        (
            "api",
            "api_collection_run",
            ApiCollectionRun,
            "collection_run_id",
            {"collectionRunId": "business", "collectionId": "collection"},
        ),
        ("ui", "case_debug", UiTestCaseRun, "run_id", {"caseId": "case", "suiteId": "suite"}),
        ("ui", "suite_run", UiTestSuiteRun, "suite_run_id", {"suiteId": "suite"}),
    ],
)
@pytest.mark.parametrize("outcome", ["success", "expired"])
@pytest.mark.asyncio
async def test_business_context_survives_reload_and_expiry(
    db, domain, kind, model, key, expected, outcome
):
    add_business_tables(db)
    fields = {key: "business", "status": "pending", "trigger_user_id": "u1"}
    if domain == "api":
        fields["environment_id"] = "env"
    for name in ("suite_id", "case_id", "collection_id"):
        if name in model.__table__.columns:
            fields[name] = {"suite_id": "suite", "case_id": "case", "collection_id": "collection"}[
                name
            ]
    run = row(model, **fields)
    task = WorkerTask(domain=domain, task_type=kind, run_id="business", task_id="queue")
    db.add_all([run, task])
    db.commit()
    db.expunge_all()
    repo = WorkerTaskRepository(AsyncSessionAdapter(db))
    service = WorkerTaskService(repo)
    claimed = await service.claim(domain, WorkerClaimRequest(workerId="worker"))
    for name, value in expected.items():
        assert claimed[name] == value
    await service.started(domain, "queue", WorkerTaskEventRequest(workerId="worker"))
    task = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "queue"))
    if outcome == "expired":
        task.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
        await service.expire_leases(domain)
        assert task.status == "failed"
        assert db.scalar(select(model)).status == "failed"
    else:
        await service.complete(
            domain, "queue", WorkerTaskEventRequest(workerId="worker", status="success")
        )
        assert task.status == "success"
        assert db.scalar(select(model)).status == "success"
    with pytest.raises(type(ErrForbidden)):
        await service.complete(
            domain, "queue", WorkerTaskEventRequest(workerId="worker", status="success")
        )


@pytest.mark.asyncio
async def test_expired_revision_preserves_output_input_and_model_for_retry(db):
    run, first = create_run(db)
    event(
        db,
        run,
        first,
        status="waiting_review",
        stage="requirement_analysis",
        config={"requirementAnalysis": {"old": True}},
    )
    run.config_json = {"requirementAnalysis": {"draft": True}, "revisionInstruction": "fix"}
    revised = enqueue(db, run, "revise", "revise")
    stage, attempts = graph(db, run)
    attempt = attempts[stage[0].active_attempt_id]
    attempt.input_snapshot_json = {**attempt.input_snapshot_json, "llmConnectionId": "fixed-model"}
    db.commit()
    service = WorkerTaskService(WorkerTaskRepository(AsyncSessionAdapter(db)))
    await service.claim("ai", WorkerClaimRequest(workerId="worker"))
    await service.started("ai", revised.task_id, WorkerTaskEventRequest(workerId="worker"))
    revised.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    await service.expire_leases("ai")
    assert run.status == "failed" and run.stage_status == "failed"
    assert run.config_json["requirementAnalysis"] == {"old": True}
    assert run.config_json["revisionInstruction"] == "fix"
    assert hydrate(db, revised).llm_connection_id == "fixed-model"
    retried = enqueue(db, run, "retry", "retry", connection_id="fixed-model")
    assert hydrate(db, retried).llm_connection_id == "fixed-model"
    latest = graph(db, run)[1][graph(db, run)[0][0].active_attempt_id]
    assert latest.input_snapshot_json["config"]["requirementAnalysis"] == {"draft": True}


@pytest.mark.parametrize(
    "status,worker,lease,error",
    [
        ("pending", "", None, ErrForbidden),
        ("running", "other", None, ErrForbidden),
        ("success", "worker", None, ErrBadRequest),
        ("failed", "worker", None, ErrBadRequest),
        ("running", "worker", -1, ErrBadRequest),
    ],
)
def test_invalid_worker_events_rejected(status, worker, lease, error):
    task = WorkerTask(status=status, worker_id=worker)
    task.lease_expires_at = (
        datetime.now(UTC) + timedelta(seconds=lease) if lease is not None else None
    )
    with pytest.raises(type(error)):
        ensure_worker_match(task, "worker")


@pytest.mark.asyncio
async def test_heartbeat_renews_from_server_clock(db):
    run, task = create_run(db)
    service = WorkerTaskService(WorkerTaskRepository(AsyncSessionAdapter(db)))
    await service.claim("ai", WorkerClaimRequest(workerId="worker"))
    before = datetime.now(UTC)
    await service.heartbeat(
        "ai",
        task.task_id,
        WorkerTaskEventRequest(workerId="worker", heartbeatAt="2099-01-01T00:00:00Z"),
    )
    lease = task.lease_expires_at.replace(tzinfo=UTC)
    assert before + timedelta(seconds=29) <= lease <= datetime.now(UTC) + timedelta(seconds=31)


@pytest.mark.asyncio
async def test_mysql_claim_skips_locked_task(mysql):
    """Opt-in: isolated synthetic domain; never dispatches work to a real Worker."""
    from uuid import uuid4

    from sqlalchemy import delete
    from sqlalchemy.orm import Session

    engine = mysql
    identifiers = ["queue-test-" + uuid4().hex for _ in range(2)]
    try:
        with Session(engine) as seed:
            seed.add_all(
                [
                    WorkerTask(domain="test", task_id=ident, task_type="lock_test", run_id=ident)
                    for ident in identifiers
                ]
            )
            seed.commit()
        with Session(engine) as first, Session(engine) as second:
            first_repo = WorkerTaskRepository(AsyncSessionAdapter(first))
            second_repo = WorkerTaskRepository(AsyncSessionAdapter(second))
            a = await first_repo.claim_pending("test")
            b = await second_repo.claim_pending("test")
            assert a.task_id in identifiers and b.task_id in identifiers
            assert a.task_id != b.task_id
            first.rollback()
            second.rollback()
    finally:
        with engine.begin() as connection:
            connection.execute(delete(WorkerTask).where(WorkerTask.task_id.in_(identifiers)))
        engine.dispose()


def test_selected_model_connection_is_stored_in_attempt_and_survives_reload(db):
    from testing_agent.services.ai_execution import persist

    run, first = create_run(db)
    event(
        db,
        run,
        first,
        status="waiting_review",
        stage="requirement_analysis",
        config={"requirementAnalysis": {"old": True}},
    )
    run.config_json = {"requirementAnalysis": {"draft": True}, "revisionInstruction": "fix"}
    run.status = "pending"
    run._operation = "revise"
    selected = WorkerTask(
        domain="ai",
        task_id="selected",
        task_type="functional_case_generate",
        run_id=run.run_id,
        llm_connection_id="selected-connection",
        status="pending",
    )
    db.add(selected)
    persist(db)
    db.commit()
    db.expunge_all()
    loaded = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "selected"))
    assert loaded.llm_connection_id is None
    assert hydrate(db, loaded).llm_connection_id == "selected-connection"


@pytest.mark.asyncio
async def test_lease_monitor_is_canceled_with_application(monkeypatch):
    import asyncio

    from testing_agent.services import worker_lease_monitor

    started, stopped = asyncio.Event(), asyncio.Event()

    async def monitor():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr(worker_lease_monitor, "monitor", monitor)
    async with worker_lease_monitor.lifespan(None):
        await asyncio.wait_for(started.wait(), 1)
    assert stopped.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,stage,field,method",
    [
        (
            "requirement_analysis",
            "extracting_text",
            "firstStepOutput",
            "revise_requirement_analysis_stage",
        ),
        (
            "functional_case_generate",
            "requirement_analysis",
            "requirementAnalysis",
            "revise_function_case_stage",
        ),
    ],
)
async def test_revision_service_preserves_model_without_queue_object_reference(
    db, kind, stage, field, method
):
    from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.services.ai_execution import persist
    from testing_agent.services.ai_generate_task import AiGenerateTaskService

    db.add(
        AiGenerateTask(
            task_id="task",
            task_type=kind,
            name="test",
            project_id="p",
            sprint_id="s",
            requirement_id="r",
            creator_user_id="u",
            source_type="text",
            source_content="sample",
            instruction="",
        )
    )
    run = AiGenerateTaskRun(
        run_id="run",
        task_id="task",
        trigger_user_id="u",
        status="pending",
        checkpoint_enabled=True,
        current_stage=stage,
        stage_status="pending",
        config_json={},
        snapshot_json={"sourceContent": "sample"},
    )
    first = WorkerTask(
        domain="ai",
        task_id="first",
        task_type=kind,
        run_id="run",
        llm_connection_id="original-model",
        status="pending",
    )
    db.add_all([run, first])
    persist(db)
    db.commit()
    event(db, run, first, status="waiting_review", stage=stage, config={field: "original"})
    db.expunge_all()
    repo = AiGenerateTaskRepository(AsyncSessionAdapter(db))
    await getattr(AiGenerateTaskService(repo), method)(
        "run",
        {"stage": stage, "revisionInstruction": "improve", "configJson": {field: "draft"}},
        "u",
    )
    db.expunge_all()
    revised = await repo.get_latest_worker_task_by_run_id("run")
    assert revised.llm_connection_id == "original-model"

    # A failed optimization must retry the same frozen inputs and connection.
    from testing_agent.services.ai_execution import worker_input

    run = await repo.get_run("run")
    event(db, run, revised, status="error", stage=stage)
    before = worker_input(db, run, revised)
    await AiGenerateTaskService(repo).retry_stage(
        "run",
        {"stage": stage},
        "u",
        kind="requirement_analysis" if kind == "requirement_analysis" else "function",
    )
    retried = await repo.get_latest_worker_task_by_run_id("run")
    assert retried.task_id != revised.task_id
    assert retried.llm_connection_id == "original-model"
    assert worker_input(db, run, retried) == before
