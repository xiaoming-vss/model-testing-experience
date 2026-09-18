import asyncio

import httpx
import pytest
from test_function_confirmed_import import FunctionImportRepository

from testing_agent.api.deps import get_ai_generate_task_service, get_current_user_id
from testing_agent.app import create_app
from testing_agent.services.ai_generate_task import AiGenerateTaskService


class ConcurrentFunctionImportRepository(FunctionImportRepository):
    def __init__(self):
        super().__init__()
        self.run_lock = asyncio.Lock()
        self.unlocked_read_count = 0
        self.unlocked_reads_ready = asyncio.Event()

    async def get_run_for_update(self, run_id: str):
        await self.run_lock.acquire()
        return await self.get_run(run_id)

    async def list_function_cases(self, suite_id: str):
        if not self.run_lock.locked():
            self.unlocked_read_count += 1
            if self.unlocked_read_count == 2:
                self.unlocked_reads_ready.set()
            await self.unlocked_reads_ready.wait()
        return await super().list_function_cases(suite_id)

    async def commit(self):
        await super().commit()
        if self.run_lock.locked():
            self.run_lock.release()

    async def rollback(self):
        await super().rollback()
        if self.run_lock.locked():
            self.run_lock.release()


@pytest.mark.asyncio
async def test_concurrent_confirmed_function_imports_only_succeed_once():
    repository = ConcurrentFunctionImportRepository()
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_ai_generate_task_service] = lambda: AiGenerateTaskService(
        repository
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        responses = await asyncio.gather(
            client.post(
                "/v1/function-case-generate-task-runs/run-1/import",
                json={"confirmOverwrite": True},
            ),
            client.post(
                "/v1/function-case-generate-task-runs/run-1/import",
                json={"confirmOverwrite": True},
            ),
        )

    assert sorted(response.status_code for response in responses) == [200, 400]
    assert repository.commits == 1
