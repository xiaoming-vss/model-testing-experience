"""How a finished task answers worker events.

Reports are acknowledged so a retry stays idempotent; a start is refused because nothing
has run yet.
"""

from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from testing_agent.core.errors import AppError, ErrForbidden, ErrWorkerLeaseLost
from testing_agent.schemas.workers import WorkerTaskEventRequest
from testing_agent.services import worker_task as module
from testing_agent.services.stage_storage.worker_service import DirectStageWorkerService
from testing_agent.services.worker_domains.events import apply_event_to_task
from testing_agent.services.worker_domains.guard import ensure_worker_match
from testing_agent.services.worker_task import WorkerTaskService

REPORTS = ["heartbeat", "complete"]
EVENTS = ["started", *REPORTS]


def _finished_task(**overrides):
    values = {
        "task_id": "task-1",
        "run_id": "run-1",
        "task_type": "api_case_debug",
        "worker_id": "worker-1",
        "status": "success",
    }
    return SimpleNamespace(**{**values, **overrides})


def _event(**overrides):
    values = {"worker_id": "worker-1", "task_id": "task-1", "run_id": "run-1"}
    return WorkerTaskEventRequest(**{**values, **overrides})


@pytest.mark.asyncio
@pytest.mark.parametrize("event", REPORTS)
async def test_late_event_from_the_owning_worker_is_acknowledged(monkeypatch, event):
    task = _finished_task()
    monkeypatch.setattr(module, "find_task", AsyncMock(return_value=task))
    authorize = AsyncMock(side_effect=AssertionError("a finished task is not re-authorized"))
    monkeypatch.setattr(module, "authorize_execution", authorize)
    service = WorkerTaskService(SimpleNamespace(session=object()))

    result = await getattr(service, event)("api", "task-1", _event())

    expected = {"taskId": "task-1", "workerId": "worker-1"}
    assert result == ({**expected, "status": "success"} if event == "complete" else expected)
    authorize.assert_not_awaited()
    # Acknowledging a late event must not touch the finished task.
    assert task.status == "success"


@pytest.mark.asyncio
@pytest.mark.parametrize("event", ["started", "complete"])
async def test_late_event_from_another_worker_is_refused(monkeypatch, event):
    task = _finished_task()
    monkeypatch.setattr(module, "find_task", AsyncMock(return_value=task))
    authorize = AsyncMock(side_effect=AssertionError("a finished task is not re-authorized"))
    monkeypatch.setattr(module, "authorize_execution", authorize)
    service = WorkerTaskService(SimpleNamespace(session=object()))

    with pytest.raises(AppError) as raised:
        await getattr(service, event)("api", "task-1", _event(worker_id="worker-2"))

    assert raised.value.code == ErrForbidden.code
    authorize.assert_not_awaited()


@pytest.mark.asyncio
async def test_late_start_is_refused_before_the_worker_runs_anything(monkeypatch):
    # Nothing has run yet, so there is nothing to acknowledge: the worker must stop.
    task = _finished_task()
    monkeypatch.setattr(module, "find_task", AsyncMock(return_value=task))
    authorize = AsyncMock(side_effect=AssertionError("a finished task is not re-authorized"))
    monkeypatch.setattr(module, "authorize_execution", authorize)
    service = WorkerTaskService(SimpleNamespace(session=object()))

    with pytest.raises(AppError) as raised:
        await service.started("api", "task-1", _event())

    assert raised.value.code == ErrWorkerLeaseLost.code
    authorize.assert_not_awaited()

    direct = DirectStageWorkerService(object())
    monkeypatch.setattr(direct, "authorize", authorize)

    with pytest.raises(AppError) as raised:
        await direct.started(task, _event())

    assert raised.value.code == ErrWorkerLeaseLost.code
    authorize.assert_not_awaited()


@pytest.mark.asyncio
async def test_late_heartbeat_only_echoes_the_callers_ids_for_any_worker(monkeypatch):
    task = _finished_task()
    monkeypatch.setattr(module, "find_task", AsyncMock(return_value=task))
    authorize = AsyncMock(side_effect=AssertionError("a finished task is not re-authorized"))
    monkeypatch.setattr(module, "authorize_execution", authorize)
    service = WorkerTaskService(SimpleNamespace(session=object()))

    result = await service.heartbeat("api", "task-1", _event(worker_id="worker-2"))

    assert result == {"taskId": "task-1", "workerId": "worker-2"}
    authorize.assert_not_awaited()
    assert task.status == "success"


@pytest.mark.asyncio
@pytest.mark.parametrize("event", EVENTS)
async def test_active_task_still_goes_through_authorization(monkeypatch, event):
    task = _finished_task(status="running")
    monkeypatch.setattr(module, "find_task", AsyncMock(return_value=task))
    authorize = AsyncMock(side_effect=ErrForbidden())
    monkeypatch.setattr(module, "authorize_execution", authorize)
    service = WorkerTaskService(SimpleNamespace(session=object()))

    with pytest.raises(AppError):
        await getattr(service, event)("api", "task-1", _event())

    authorize.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("event", REPORTS)
async def test_direct_stage_late_event_is_acknowledged_for_every_task_type(monkeypatch, event):
    task = _finished_task(task_type="test_report_generate", status="failed")
    service = DirectStageWorkerService(object())
    authorize = AsyncMock(side_effect=AssertionError("a finished task is not re-authorized"))
    monkeypatch.setattr(service, "authorize", authorize)

    result = await getattr(service, event)(task, _event())

    expected = {"taskId": "task-1", "workerId": "worker-1"}
    assert result == ({**expected, "status": "failed"} if event == "complete" else expected)
    authorize.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [400, 404])
async def test_obsolete_attempt_is_left_alone_when_its_task_is_retired(code):
    task = _finished_task(status="running")
    service = DirectStageWorkerService(
        SimpleNamespace(
            scalar=AsyncMock(return_value=SimpleNamespace(stage_id="stage", id="attempt"))
        )
    )
    service.transitions = SimpleNamespace(
        failed=AsyncMock(side_effect=AppError(code, "obsolete", 500))
    )

    await service._fail_attempt(task, "message")


@pytest.mark.asyncio
async def test_unexpected_stage_error_is_not_swallowed():
    task = _finished_task(status="running")
    service = DirectStageWorkerService(
        SimpleNamespace(
            scalar=AsyncMock(return_value=SimpleNamespace(stage_id="stage", id="attempt"))
        )
    )
    unexpected = AppError(500, "boom", 500)
    service.transitions = SimpleNamespace(failed=AsyncMock(side_effect=unexpected))

    with pytest.raises(AppError) as raised:
        await service._fail_attempt(task, "message")

    assert raised.value is unexpected


@pytest.mark.asyncio
async def test_retiring_a_task_without_an_attempt_still_closes_the_queue_row():
    task = _finished_task(status="running")
    service = DirectStageWorkerService(SimpleNamespace(scalar=AsyncMock(return_value=None)))

    await service.retire_authorization(task)

    assert task.status == "failed"
    assert task.finished_at is not None


@pytest.mark.asyncio
async def test_canceled_task_gets_a_finished_time_without_a_reported_one():
    task = SimpleNamespace(worker_id="", status="claimed", finished_at=None)
    del task.finished_at

    await apply_event_to_task(task, WorkerTaskEventRequest(worker_id="worker-1"), "canceled")

    assert task.finished_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("call", ["heartbeat", "control_state"])
@pytest.mark.parametrize("state", ["requeued", "expired"])
async def test_event_outside_a_live_lease_is_a_conflict(monkeypatch, call, state):
    # Workers end the execution on 409; a 400 is a request they sent wrong.
    stale = {"status": "pending"} if state == "requeued" else {"status": "running"}
    task = _finished_task(
        **stale,
        lease_expires_at=datetime.now(UTC) - timedelta(seconds=1 if state == "expired" else -60),
    )
    monkeypatch.setattr(module, "find_task", AsyncMock(return_value=task))
    authorize = AsyncMock()
    monkeypatch.setattr(module, "authorize_execution", authorize)
    service = WorkerTaskService(SimpleNamespace(session=object()))

    with pytest.raises(AppError) as raised:
        if call == "heartbeat":
            await service.heartbeat("api", "task-1", _event())
        else:
            await service.control_state("api", "task-1", "worker-1")

    assert raised.value.http_code == HTTPStatus.CONFLICT
    assert raised.value.code == ErrWorkerLeaseLost.code


def test_missing_worker_identity_is_still_a_bad_request():
    with pytest.raises(AppError) as raised:
        ensure_worker_match(_finished_task(status="running"), " ")

    assert raised.value.http_code == HTTPStatus.BAD_REQUEST
