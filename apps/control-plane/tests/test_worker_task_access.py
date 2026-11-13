from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from testing_agent.core.errors import AppError, ErrBadRequest, ErrForbidden
from testing_agent.schemas.workers import WorkerClaimRequest
from testing_agent.services import worker_task as module
from testing_agent.services.worker_task import WorkerTaskService


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["allowed", "missing", "revoked"])
async def test_ai_task_access_always_checks_current_authority(monkeypatch, outcome):
    task = SimpleNamespace(task_id="task")
    repository = SimpleNamespace(
        session=object(),
        get_worker_task=AsyncMock(return_value=None if outcome == "missing" else task),
    )
    authorize = AsyncMock(side_effect=ErrForbidden() if outcome == "revoked" else None)
    direct = SimpleNamespace(is_direct=AsyncMock(return_value=True), authorize=authorize)
    monkeypatch.setattr(module, "DirectStageWorkerService", lambda session: direct)
    service = WorkerTaskService(repository)

    if outcome == "allowed":
        assert await service.ai_worker_task("task") is task
    else:
        with pytest.raises(AppError) as error:
            await service.ai_worker_task("task")
        assert error.value.code == (404 if outcome == "missing" else 403)

    repository.get_worker_task.assert_awaited_once_with("ai", "task")
    if outcome == "missing":
        authorize.assert_not_awaited()
    else:
        authorize.assert_awaited_once_with(task)


@pytest.mark.parametrize("standalone", [True, False])
@pytest.mark.parametrize("error", [ErrBadRequest, ErrForbidden])
async def test_ai_claim_suppresses_only_forbidden_errors(monkeypatch, standalone, error):
    task = SimpleNamespace(task_id="task")
    repository = SimpleNamespace(session=object(), claim_pending=AsyncMock(return_value=task))
    service = WorkerTaskService(repository)
    first = SimpleNamespace(
        is_standalone=AsyncMock(return_value=standalone), claim=AsyncMock(side_effect=error())
    )
    direct = SimpleNamespace(
        is_direct=AsyncMock(return_value=True), claim=AsyncMock(side_effect=error())
    )
    monkeypatch.setattr(module, "StandaloneWorkerService", lambda _: first)
    monkeypatch.setattr(module, "DirectStageWorkerService", lambda _: direct)
    if error is ErrForbidden:
        assert await service.claim("ai", WorkerClaimRequest(worker_id="worker")) is None
    else:
        with pytest.raises(AppError) as raised:
            await service.claim("ai", WorkerClaimRequest(worker_id="worker"))
        assert raised.value.code == ErrBadRequest.code
