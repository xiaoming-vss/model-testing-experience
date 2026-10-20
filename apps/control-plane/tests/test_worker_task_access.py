from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from support.execution_writer import MemoryExecutionWriter

from testing_agent.core.errors import AppError, ErrForbidden
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
    monkeypatch.setattr(module, "authorize_execution", authorize)
    service = WorkerTaskService(repository, execution_writer=MemoryExecutionWriter())

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
        authorize.assert_awaited_once_with(repository.session, task)
