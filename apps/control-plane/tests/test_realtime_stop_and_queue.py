from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter  # noqa: F401
from support.worker_queue_storage import add_business_tables, row
from support.worker_queue_storage import db as db

from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.worker_task import WorkerTaskRepository
from testing_agent.services import test_run_stop


@pytest.mark.asyncio
@pytest.mark.parametrize("domain", ["api", "ui"])
async def test_project_access_revocation_closes_suite_items_and_notifies(db, monkeypatch, domain):
    from support.api_run_scope import seed, services

    from testing_agent.core.errors import ErrForbidden
    from testing_agent.models.api_collection_run import ApiCollectionRunItem
    from testing_agent.models.project_member import ProjectMember
    from testing_agent.models.ui_test_suite_run import UiTestSuiteRunItem
    from testing_agent.repositories.ui_test_case_run import UiTestCaseRunRepository
    from testing_agent.schemas.api_run import RunApiCollectionRequest
    from testing_agent.schemas.ui_run import RunUiSuiteRequest
    from testing_agent.services import test_run_notifications, worker_authorization
    from testing_agent.services.ui_test_case_run import UiTestCaseRunService

    seed(db)
    member = ProjectMember(project_id="p1", user_id="u2", role="member")
    db.add(member)
    db.commit()
    if domain == "api":
        _, service = services(db)
        run = await service.run("u2", "collection", RunApiCollectionRequest(environmentId="env"))
        run_id, item_model, field = (
            run["collectionRunId"],
            ApiCollectionRunItem,
            "collection_run_id",
        )
    else:
        service = UiTestCaseRunService(UiTestCaseRunRepository(AsyncSessionAdapter(db)))
        run = await service.run_suite("u2", "suite", RunUiSuiteRequest(environmentId="ui-env"))
        run_id, item_model, field = run["suiteRunId"], UiTestSuiteRunItem, "suite_run_id"
    task = db.scalar(select(WorkerTask).where(WorkerTask.run_id == run_id))
    item = db.scalar(select(item_model).where(getattr(item_model, field) == run_id))
    item.status = "running"
    if domain == "ui":
        item.step_results_json = [{"orderNo": 1, "status": "running"}]
    pending = row(
        item_model, item_id="later", case_id=item.case_id, status="pending", **{field: run_id}
    )
    db.add(pending)
    task.status = "running"
    db.delete(member)
    db.commit()
    notifications = []

    async def notify_run(kind, value):
        assert (
            db.scalar(select(WorkerTask).where(WorkerTask.task_id == task.task_id)).status
            == "failed"
        )
        notifications.append((kind, value))

    async def notify_control(value):
        notifications.append(("control", value))

    monkeypatch.setattr(test_run_notifications, "notify_run_changed", notify_run)
    monkeypatch.setattr(test_run_notifications, "notify_task_control", notify_control)
    with pytest.raises(type(ErrForbidden)):
        await worker_authorization.authorize_execution(AsyncSessionAdapter(db), task)
    db.refresh(item)
    db.refresh(pending)
    assert (item.status, pending.status) == ("error", "skipped")
    assert "授权已失效" in item.error_message
    if domain == "ui":
        assert item.step_results_json[0]["status"] == "error"
    assert notifications == [(domain, run_id), ("control", task.task_id)]


@pytest.mark.asyncio
async def test_claim_order_is_shared_by_api_and_ui_queues(db):
    now = datetime.now(UTC)
    db.add_all(
        [
            WorkerTask(
                domain="api",
                task_id="new",
                task_type="api_case_debug",
                run_id="b",
                status="pending",
                created_at=now,
            ),
            WorkerTask(
                domain="ui",
                task_id="old",
                task_type="case_debug",
                run_id="a",
                status="pending",
                created_at=now - timedelta(seconds=1),
            ),
        ]
    )
    db.commit()
    task = await WorkerTaskRepository(AsyncSessionAdapter(db)).claim_oldest_api_ui()
    assert task.task_id == "old"


@pytest.mark.asyncio
@pytest.mark.parametrize("initial,expected", [("pending", "canceled"), ("running", "stopping")])
async def test_stop_persists_intent_after_permission_check(db, monkeypatch, initial, expected):
    add_business_tables(db)
    run = row(
        ApiCaseRun,
        run_id="run",
        case_id="case",
        collection_id="collection",
        environment_id="env",
        trigger_user_id="owner",
        status=initial,
    )
    task = WorkerTask(
        domain="api", task_id="task", task_type="api_case_debug", run_id="run", status=initial
    )
    db.add_all([run, task])
    db.commit()
    calls = []

    async def accessible(user, case, *, action):
        calls.append((user, case, action))

    async def notify(*args):
        calls.append(args)

    monkeypatch.setattr(test_run_stop, "notify_run_changed", notify)
    monkeypatch.setattr(test_run_stop, "notify_task_control", notify)
    repository = SimpleNamespace(get_run=lambda _: _async_value(run))
    api = SimpleNamespace(repository=repository, get_accessible_context=accessible)
    result = await test_run_stop.stop_run(
        "api-case", "run", "owner", AsyncSessionAdapter(db), api, None, None
    )
    assert result["status"] == expected
    assert task.status == run.status == expected
    assert calls[0] == ("owner", "case", "execute")
    assert calls[1] == ("api", "run")
    assert (("task",) in calls) == (initial == "running")


async def _async_value(value):
    return value


@pytest.mark.asyncio
@pytest.mark.parametrize("domain", ["api", "ui"])
async def test_fast_debug_cleanup_cannot_remove_initial_response(db, monkeypatch, domain):
    """A Worker can finish and delete the run as soon as its wake-up is sent."""
    from sqlalchemy import select
    from support.api_run_scope import seed, services

    from testing_agent.models.ui_test_case_run import UiTestCaseRun
    from testing_agent.repositories.ui_test_case_run import UiTestCaseRunRepository
    from testing_agent.schemas.api_run import RunApiCaseRequest
    from testing_agent.schemas.ui_run import DebugRunUiCaseRequest
    from testing_agent.services import test_run_notifications
    from testing_agent.services.ui_test_case_run import UiTestCaseRunService

    seed(db)
    run_model = ApiCaseRun if domain == "api" else UiTestCaseRun

    async def finish_immediately():
        task = db.scalar(select(WorkerTask).where(WorkerTask.domain == domain))
        run = db.scalar(select(run_model).where(run_model.run_id == task.run_id))
        db.delete(task)
        db.delete(run)
        db.commit()

    monkeypatch.setattr(test_run_notifications, "notify_task_available", finish_immediately)
    if domain == "api":
        service, _ = services(db)
        initial = await service.run(
            "u1", "api-case", RunApiCaseRequest(environmentId="env"), live_debug=True
        )
    else:
        service = UiTestCaseRunService(UiTestCaseRunRepository(AsyncSessionAdapter(db)))
        initial = await service.debug_run_case(
            "u1", "case", DebugRunUiCaseRequest(environmentId="ui-env"), live_debug=True
        )
    assert initial["runId"]
    assert initial["status"] == "pending"
    assert db.scalar(select(run_model)) is None


@pytest.mark.asyncio
async def test_live_api_execution_checks_current_ownership_and_missing_case(db):
    from support.api_run_scope import seed, services

    from testing_agent.core.errors import ErrForbidden, ErrNotFound
    from testing_agent.schemas.api_run import RunApiCaseRequest

    seed(db)
    service, _ = services(db)
    request = RunApiCaseRequest(environmentId="env", liveDebug=True)
    with pytest.raises(type(ErrForbidden)):
        await service.run("u2", "api-case", request)
    with pytest.raises(type(ErrNotFound)):
        await service.run("u1", "missing", request)


@pytest.mark.asyncio
async def test_claiming_live_api_debug_keeps_lease_and_updates_run(db, monkeypatch):
    from sqlalchemy import select
    from support.api_run_scope import seed, services

    from testing_agent.schemas.api_run import RunApiCaseRequest
    from testing_agent.schemas.workers import WorkerClaimRequest
    from testing_agent.services import worker_task

    seed(db)
    service, _ = services(db)
    initial = await service.run(
        "u1", "api-case", RunApiCaseRequest(environmentId="env"), live_debug=True
    )
    monkeypatch.setattr(worker_task, "notify_run_changed", lambda *args: _async_value(None))
    worker = worker_task.WorkerTaskService(WorkerTaskRepository(AsyncSessionAdapter(db)))
    claimed = await worker.claim_api_ui(WorkerClaimRequest(workerId="worker"))
    run = db.scalar(select(ApiCaseRun).where(ApiCaseRun.run_id == initial["runId"]))
    task = db.scalar(select(WorkerTask).where(WorkerTask.run_id == initial["runId"]))
    assert claimed["runId"] == run.run_id
    assert claimed["caseId"] == "api-case"
    assert claimed["status"] == "claimed" and task.worker_id == "worker"
    assert run.status == "queued" and task.lease_expires_at is not None


@pytest.mark.asyncio
async def test_stop_winning_the_lock_prevents_late_success_from_overwriting_canceled(
    db, monkeypatch
):
    from testing_agent.schemas.workers import WorkerTaskEventRequest
    from testing_agent.services import worker_task as module

    add_business_tables(db)
    run = row(
        ApiCaseRun,
        run_id="run",
        case_id="case",
        collection_id="collection",
        environment_id="env",
        trigger_user_id="owner",
        status="stopping",
    )
    task = WorkerTask(
        domain="api",
        task_id="task",
        task_type="api_case_debug",
        run_id="run",
        status="stopping",
        worker_id="worker",
    )
    db.add_all([run, task])
    db.commit()

    async def authorize(*args, **kwargs):
        return SimpleNamespace(run=run)

    async def notify(*args):
        return None

    monkeypatch.setattr(module, "authorize_execution", authorize)
    monkeypatch.setattr(module, "notify_run_changed", notify)
    service = module.WorkerTaskService(WorkerTaskRepository(AsyncSessionAdapter(db)))
    result = await service.complete(
        "api", "task", WorkerTaskEventRequest(workerId="worker", status="success")
    )
    assert result["status"] == "canceled"
    assert run.status == task.status == "canceled"


@pytest.mark.asyncio
async def test_live_api_result_is_sent_before_records_are_deleted(db, monkeypatch):
    from sqlalchemy import select

    from testing_agent.services import live_debug_cleanup

    add_business_tables(db)
    run = row(
        ApiCaseRun,
        run_id="run",
        case_id="case",
        collection_id="collection",
        environment_id="env",
        trigger_user_id="owner",
        trigger_type="live_debug",
        status="success",
        response_snapshot_json={"statusCode": 200, "body": "done"},
    )
    task = WorkerTask(
        domain="api",
        task_id="task",
        task_type="api_case_debug",
        run_id="run",
        status="success",
        worker_id="worker",
    )
    db.add_all([run, task])
    db.commit()
    events = []

    async def publish(domain, run_id, payload):
        assert db.scalar(select(ApiCaseRun).where(ApiCaseRun.run_id == run_id)) is not None
        events.append((domain, run_id, payload))

    monkeypatch.setattr(live_debug_cleanup, "notify_run_finished", publish)
    assert await live_debug_cleanup.finish_api_debug(AsyncSessionAdapter(db), "task")
    assert events[0][2]["response"]["body"] == "done"
    assert db.scalar(select(ApiCaseRun).where(ApiCaseRun.run_id == "run")) is None
    assert db.scalar(select(WorkerTask).where(WorkerTask.task_id == "task")) is None


@pytest.mark.asyncio
async def test_recovery_removes_only_terminal_live_debug_records(db, monkeypatch):
    from sqlalchemy import select

    from testing_agent.services import live_debug_cleanup

    add_business_tables(db)
    for run_id, trigger, status in (
        ("retire", "live_debug", "error"),
        ("active", "live_debug", "running"),
        ("legacy", "manual", "success"),
    ):
        db.add(
            row(
                ApiCaseRun,
                run_id=run_id,
                case_id="case",
                collection_id="collection",
                environment_id="env",
                trigger_user_id="owner",
                trigger_type=trigger,
                status=status,
            )
        )
        db.add(
            WorkerTask(
                domain="api",
                task_id=run_id,
                task_type="api_case_debug",
                run_id=run_id,
                status=status,
            )
        )
    db.commit()

    async def publish(*args):
        return None

    monkeypatch.setattr(live_debug_cleanup, "notify_run_finished", publish)
    assert await live_debug_cleanup.recover_api_debug_runs(AsyncSessionAdapter(db)) == 1
    assert set(db.scalars(select(ApiCaseRun.run_id))) == {"active", "legacy"}


@pytest.mark.asyncio
@pytest.mark.parametrize("domain", ["api", "ui"])
async def test_recovery_scan_moves_past_failed_page_and_revisits_it(db, monkeypatch, domain):
    from testing_agent.models.ui_test_case_run import UiTestCaseRun
    from testing_agent.services import live_debug_cleanup

    add_business_tables(db)
    for number in range(3):
        run_id = f"scan-{number}"
        common = dict(
            run_id=run_id,
            case_id="case",
            environment_id="env",
            trigger_user_id="owner",
            trigger_type="live_debug",
            status="error",
        )
        if domain == "api":
            db.add(row(ApiCaseRun, collection_id="collection", **common))
        else:
            db.add(row(UiTestCaseRun, suite_id="suite", **common))
        db.add(
            WorkerTask(
                domain=domain,
                task_id=run_id,
                task_type="api_case_debug" if domain == "api" else "case_debug",
                run_id=run_id,
                status="error",
            )
        )
    db.commit()
    calls = []
    fail_oldest = True

    async def finish(session, task_id):
        calls.append(task_id)
        if fail_oldest and task_id in {"scan-0", "scan-1"}:
            raise RuntimeError("temporary")
        return True

    name = "finish_api_debug" if domain == "api" else "finish_ui_debug"
    monkeypatch.setattr(live_debug_cleanup, name, finish)
    recover = (
        live_debug_cleanup.recover_api_debug_runs
        if domain == "api"
        else live_debug_cleanup.recover_ui_debug_runs
    )
    cursor = live_debug_cleanup.DebugCleanupCursor()
    session = AsyncSessionAdapter(db)
    assert await recover(session, limit=2, cursor=cursor) == 0
    new_run = dict(
        run_id="scan-new",
        case_id="case",
        environment_id="env",
        trigger_user_id="owner",
        trigger_type="live_debug",
        status="error",
    )
    if domain == "api":
        db.add(row(ApiCaseRun, collection_id="collection", **new_run))
    else:
        db.add(row(UiTestCaseRun, suite_id="suite", **new_run))
    db.add(
        WorkerTask(
            domain=domain,
            task_id="scan-new",
            task_type="api_case_debug" if domain == "api" else "case_debug",
            run_id="scan-new",
            status="error",
        )
    )
    db.commit()
    assert await recover(session, limit=2, cursor=cursor) == 1
    assert calls == ["scan-0", "scan-1", "scan-2"]
    fail_oldest = False
    assert await recover(session, limit=2, cursor=cursor) == 2
    assert calls[-2:] == ["scan-0", "scan-1"]


@pytest.mark.asyncio
@pytest.mark.parametrize("connected,failed", [(True, False), (True, True), (False, False)])
async def test_live_ui_delivers_screenshot_before_retiring_run_and_file(
    db, monkeypatch, connected, failed
):
    from sqlalchemy import select

    from testing_agent.core import config
    from testing_agent.models.stored_file import StoredFile
    from testing_agent.models.ui_test_case_run import UiTestCaseRun
    from testing_agent.services import live_debug_cleanup, live_debug_transfer, stored_file

    add_business_tables(db)
    StoredFile.__table__.create(db.get_bind(), checkfirst=True)
    run = row(
        UiTestCaseRun,
        run_id="run-ui",
        case_id="case",
        suite_id="suite",
        environment_id="env",
        trigger_user_id="owner",
        trigger_type="live_debug",
        status="success",
        step_results_json=[{"orderNo": 1, "screenshotPath": "/v1/files/file-1/download"}],
    )
    task = WorkerTask(
        domain="ui", task_id="task-ui", task_type="case_debug", run_id="run-ui", status="success"
    )
    file = row(
        StoredFile,
        file_id="file-1",
        filename="step.png",
        bucket="bucket",
        object_key="object",
        resource_type="ui_worker_task",
        resource_id="task-ui",
        status="attached",
        expires_at=datetime.now(UTC),
    )
    db.add_all([run, task, file])
    db.commit()
    events = []

    class StorageService:
        def __init__(self, session, settings):
            pass

        async def cleanup(self):
            events.append("cleanup attempted")

    async def publish(domain, run_id, payload):
        assert db.scalar(select(UiTestCaseRun).where(UiTestCaseRun.run_id == run_id)) is not None
        events.append(payload)

    async def transfer(run_id, files):
        assert connected
        assert run_id == "run-ui"
        assert files[0]["path"] == "/v1/files/file-1/download"
        events.append("artifact delivered")
        return {files[0]["path"]} if failed else set()

    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(s3=object()))
    monkeypatch.setattr(stored_file, "StoredFileService", StorageService)
    monkeypatch.setattr(live_debug_cleanup, "notify_run_finished", publish)
    monkeypatch.setattr(live_debug_transfer, "request_ui_artifact_delivery", transfer)
    monkeypatch.setattr(
        live_debug_cleanup, "has_run_subscribers", lambda *args: _async_value(connected)
    )
    assert await live_debug_cleanup.finish_ui_debug(AsyncSessionAdapter(db), "task-ui")
    if connected:
        assert events.pop(0) == "artifact delivered"
    expected_path = "/v1/files/file-1/download" if connected and not failed else ""
    assert events[0]["stepResults"][0]["screenshotPath"] == expected_path
    if not expected_path:
        assert "部分临时产物读取失败" in events[0]["errorMessage"]
    assert events[1] == "cleanup attempted"
    assert db.scalar(select(UiTestCaseRun).where(UiTestCaseRun.run_id == "run-ui")) is None
    assert db.scalar(select(WorkerTask).where(WorkerTask.task_id == "task-ui")) is None
    assert db.scalar(select(StoredFile).where(StoredFile.file_id == "file-1")).status == "deleting"


@pytest.mark.asyncio
async def test_live_ui_artifact_is_delivered_and_deleted_from_real_s3(db, monkeypatch):
    import os
    import uuid

    from botocore.exceptions import ClientError

    from testing_agent.core import config
    from testing_agent.core.object_storage import ObjectStorage, ObjectStorageSettings
    from testing_agent.models.stored_file import StoredFile
    from testing_agent.models.ui_test_case_run import UiTestCaseRun
    from testing_agent.services import live_debug_cleanup, live_debug_transfer

    endpoint = os.environ.get("REALTIME_TEST_S3_ENDPOINT")
    if not endpoint:
        pytest.skip("Set REALTIME_TEST_S3_ENDPOINT to an isolated disposable S3 endpoint")
    settings = ObjectStorageSettings(
        enabled=True,
        endpoint=endpoint,
        bucket="realtime-" + uuid.uuid4().hex[:12],
        access_key="mtxaccesskey",
        secret_key="mtxsecretkey123",
    )
    storage = ObjectStorage(settings)
    storage.client.create_bucket(Bucket=settings.bucket)
    try:
        storage.client.put_object(Bucket=settings.bucket, Key="shot.png", Body=b"test screenshot")
        add_business_tables(db)
        db.add(
            row(
                UiTestCaseRun,
                run_id="run-ui-real",
                case_id="case",
                suite_id="suite",
                environment_id="env",
                trigger_user_id="owner",
                trigger_type="live_debug",
                status="success",
                step_results_json=[
                    {
                        "orderNo": 1,
                        "screenshotPath": "/v1/files/file-real/download",
                    }
                ],
            )
        )
        db.add(
            WorkerTask(
                domain="ui",
                task_id="task-ui-real",
                task_type="case_debug",
                run_id="run-ui-real",
                status="success",
            )
        )
        db.add(
            row(
                StoredFile,
                file_id="file-real",
                filename="shot.png",
                bucket=settings.bucket,
                object_key="shot.png",
                staging_key="",
                verification_id="",
                cleanup_id="",
                resource_type="ui_worker_task",
                resource_id="task-ui-real",
                status="attached",
                expires_at=datetime.now(UTC),
            )
        )
        db.commit()
        delivered = []

        async def publish(domain, run_id, result):
            delivered.append(result)

        async def transfer(run_id, files):
            body = storage.client.get_object(Bucket=files[0]["bucket"], Key=files[0]["key"])["Body"]
            try:
                assert body.read() == b"test screenshot"
            finally:
                body.close()
            return set()

        monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(s3=settings))
        monkeypatch.setattr(live_debug_cleanup, "notify_run_finished", publish)
        monkeypatch.setattr(live_debug_transfer, "request_ui_artifact_delivery", transfer)
        monkeypatch.setattr(
            live_debug_cleanup, "has_run_subscribers", lambda *args: _async_value(True)
        )
        assert await live_debug_cleanup.finish_ui_debug(AsyncSessionAdapter(db), "task-ui-real")
        assert delivered[0]["stepResults"][0]["screenshotPath"] == "/v1/files/file-real/download"
        with pytest.raises(ClientError) as error:
            storage.client.head_object(Bucket=settings.bucket, Key="shot.png")
        assert error.value.response["ResponseMetadata"]["HTTPStatusCode"] == 404
    finally:
        storage.client.delete_object(Bucket=settings.bucket, Key="shot.png")
        storage.client.delete_bucket(Bucket=settings.bucket)


@pytest.mark.asyncio
async def test_ui_debug_cleanup_recovers_terminal_run_after_process_restart(db, monkeypatch):
    from sqlalchemy import select

    from testing_agent.core import config
    from testing_agent.models.ui_test_case_run import UiTestCaseRun
    from testing_agent.services import live_debug_cleanup, stored_file

    add_business_tables(db)
    db.add(
        row(
            UiTestCaseRun,
            run_id="recovered-ui",
            case_id="case",
            suite_id="suite",
            environment_id="env",
            trigger_user_id="u1",
            trigger_type="live_debug",
            status="success",
        )
    )
    db.add(
        WorkerTask(
            domain="ui",
            task_id="recovered-task",
            task_type="case_debug",
            run_id="recovered-ui",
            status="success",
        )
    )
    db.commit()

    class StorageService:
        def __init__(self, session, settings):
            pass

    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(s3=object()))
    monkeypatch.setattr(stored_file, "StoredFileService", StorageService)
    monkeypatch.setattr(live_debug_cleanup, "notify_run_finished", lambda *args: _async_value(None))
    assert await live_debug_cleanup.recover_ui_debug_runs(AsyncSessionAdapter(db)) == 1
    assert db.scalar(select(UiTestCaseRun).where(UiTestCaseRun.run_id == "recovered-ui")) is None
    assert db.scalar(select(WorkerTask).where(WorkerTask.task_id == "recovered-task")) is None
