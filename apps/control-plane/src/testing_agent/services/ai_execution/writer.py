"""Explicit execution persistence inside the caller's transaction; never commits."""

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.ai_execution_intent import ExecutionIntent
from testing_agent.models.ai_generate_task import AiGenerateTaskRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.ai_execution import persist_run


class ExecutionWriter(Protocol):
    async def save(
        self,
        session: AsyncSession,
        run: AiGenerateTaskRun,
        *,
        intent: ExecutionIntent = ExecutionIntent(),
        worker: WorkerTask | None = None,
    ) -> None: ...


class SqlExecutionWriter:
    async def save(
        self,
        session: AsyncSession,
        run: AiGenerateTaskRun,
        *,
        intent: ExecutionIntent = ExecutionIntent(),
        worker: WorkerTask | None = None,
    ) -> None:
        await session.run_sync(lambda sync: persist_run(sync, run, intent=intent, worker=worker))
