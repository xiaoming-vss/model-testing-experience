"""API ownership normalization, Worker child execution, and historical rollback."""

import pytest
from sqlalchemy import select
from test_ai_execution_storage import AsyncSessionAdapter
from test_ai_execution_storage import db as db
from test_ui_run_scope import seed as seed_ui
from test_worker_queue_storage import row

from testing_agent.core.errors import ErrForbidden, ErrNotFound
from testing_agent.db.base import Base
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.api_collection_run import ApiCollectionRun, ApiCollectionRunItem
from testing_agent.models.api_environment import ApiEnvironment
from testing_agent.models.api_environment_var import ApiEnvironmentVar
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint_daily_metrics import SprintDailyMetrics
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.api_case import ApiCaseRepository
from testing_agent.repositories.api_collection_run import ApiCollectionRunRepository
from testing_agent.repositories.sprint_daily_metrics import SprintDailyMetricsRepository
from testing_agent.repositories.worker_task import WorkerTaskRepository
from testing_agent.schemas.api_run import RunApiCaseRequest, RunApiCollectionRequest
from testing_agent.schemas.workers import WorkerClaimRequest, WorkerTaskEventRequest
from testing_agent.services.api_case import ApiCaseService
from testing_agent.services.api_collection_run import ApiCollectionRunService
from testing_agent.services.worker_task import WorkerTaskService


def seed(db):
    seed_ui(db)
    models = (
        ApiCase,
        ApiCollection,
        ApiCaseRun,
        ApiCollectionRun,
        ApiCollectionRunItem,
        ApiEnvironment,
        ApiEnvironmentVar,
    )
    Base.metadata.create_all(db.get_bind(), tables=[m.__table__ for m in models])
    for item in [
        row(ApiCollection, collection_id="collection", requirement_id="req"),
        row(
            ApiCase,
            case_id="api-case",
            collection_id="collection",
            method="GET",
            url_template="/ping",
        ),
        row(
            ApiEnvironment,
            environment_id="env",
            project_id="p1",
            base_url="https://example.test",
        ),
    ]:
        db.add(item)
        db.flush()
    history = db.scalar(select(SprintDailyMetrics))
    history.api_case_total = 11
    history.api_case_success = 9
    db.commit()


def services(db):
    adapter = AsyncSessionAdapter(db)
    return (
        ApiCaseService(ApiCaseRepository(adapter)),
        ApiCollectionRunService(ApiCollectionRunRepository(adapter)),
    )


@pytest.mark.asyncio
async def test_api_run_scope_changes_permissions_and_statistics_with_requirement(db):
    seed(db)
    cases, collections = services(db)
    single = await cases.run("u1", "api-case", RunApiCaseRequest(environmentId="env"))
    group = await collections.run("u1", "collection", RunApiCollectionRequest(environmentId="env"))
    assert group["projectId"] == "p1"
    assert single["collectionId"] == "collection"
    assert group["sprintId"] == "s1"
    stored = db.scalar(select(ApiCaseRun))
    stored.status = "success"
    db.commit()
    metrics = SprintDailyMetricsRepository(AsyncSessionAdapter(db))
    assert await metrics.list_latest_api_run_statuses("s1") == {"api-case": "success"}
    db.scalar(select(Requirement)).sprint_id = "s2"
    db.commit()
    assert await metrics.list_latest_api_run_statuses("s1") == {}
    assert await metrics.list_latest_api_run_statuses("s2") == {"api-case": "success"}
    with pytest.raises(type(ErrForbidden)):
        await cases.get_run("u1", single["runId"])
    with pytest.raises(type(ErrForbidden)):
        await collections.report("u1", group["collectionRunId"])
    assert (await cases.get_run("u2", single["runId"]))["runId"] == single["runId"]
    assert (await collections.get("u2", group["collectionRunId"]))["sprintId"] == "s2"
    from testing_agent.repositories.deletion import delete_resource

    adapter = AsyncSessionAdapter(db)
    for case in list(db.scalars(select(ApiCase))):
        await delete_resource(adapter, case)
    await delete_resource(adapter, db.scalar(select(ApiCollection)))
    db.commit()
    assert await metrics.list_latest_api_run_statuses("s2") == {}
    with pytest.raises(type(ErrNotFound)):
        await cases.get_run("u2", single["runId"])
    with pytest.raises(type(ErrNotFound)):
        await collections.report("u2", group["collectionRunId"])
    assert db.scalar(select(SprintDailyMetrics)).api_case_total == 11
    assert db.scalar(select(SprintDailyMetrics)).api_case_success == 9


@pytest.mark.asyncio
async def test_worker_child_run_needs_no_scope_columns_and_remains_readable(db):
    seed(db)
    cases, collections = services(db)
    group = await collections.run("u1", "collection", RunApiCollectionRequest(environmentId="env"))
    workers = WorkerTaskService(WorkerTaskRepository(AsyncSessionAdapter(db)))
    claimed = await workers.claim("api", WorkerClaimRequest(workerId="worker"))
    await workers.started("api", claimed["taskId"], WorkerTaskEventRequest(workerId="worker"))
    item = db.scalar(select(ApiCollectionRunItem))
    await workers.complete_api_collection_item(
        claimed["taskId"],
        item.item_id,
        WorkerTaskEventRequest(
            workerId="worker",
            status="success",
            request={"method": "GET"},
            response={"statusCode": 200},
        ),
    )
    await workers.complete(
        "api", claimed["taskId"], WorkerTaskEventRequest(workerId="worker", status="success")
    )
    child = await cases.get_run("u1", item.case_run_id)
    assert child["collectionId"] == "collection"
    report = await collections.report("u1", group["collectionRunId"])
    assert report["success"] and report["items"][0]["response"]["statusCode"] == 200
    assert db.scalar(select(WorkerTask)).status == "success"


@pytest.mark.asyncio
async def test_orphan_run_has_no_authorizing_scope(db):
    seed(db)
    _, collections = services(db)
    from sqlalchemy.exc import IntegrityError

    db.add(row(ApiCollectionRun, collection_run_id="orphan", collection_id="gone"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    with pytest.raises(type(ErrNotFound)):
        await collections.get("u1", "orphan")
