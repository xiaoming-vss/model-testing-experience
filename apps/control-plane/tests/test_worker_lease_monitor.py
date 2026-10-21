"""Recovery remains live without foreground claims and isolates failed domains."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from testing_agent.services import integration_lifecycle, worker_lease_monitor


async def test_sweep_bounds_transactions_and_continues_after_domain_failure(monkeypatch, caplog):
    sessions = []
    calls = []

    @asynccontextmanager
    async def factory():
        session = AsyncMock()
        sessions.append(session)
        try:
            yield session
        finally:
            await session.close()

    async def expire(self, domain):
        calls.append(domain)
        if domain == "ai":
            raise RuntimeError("secret must not be logged")
        return 100 if domain == "api" else 0

    integration = AsyncMock()
    integration.expire.return_value = 0
    monkeypatch.setattr(worker_lease_monitor.WorkerTaskService, "expire_leases", expire)
    monkeypatch.setattr(integration_lifecycle, "lifecycle", lambda session: integration)
    await worker_lease_monitor.sweep_once(factory)
    assert calls == ["ai", *(["api"] * 5), "ui"]
    assert len(sessions) == 8 and all(session.close.await_count == 1 for session in sessions)
    integration.expire.assert_awaited_once()
    assert "RuntimeError" in caplog.text and "secret must not be logged" not in caplog.text
    assert sessions[-1].commit.await_count == 1


async def test_monitor_recovers_on_startup_and_retries_next_interval(monkeypatch):
    calls = []

    async def sweep():
        calls.append("sweep")
        if calls.count("sweep") == 1:
            raise RuntimeError("temporary")

    async def sleep(seconds):
        calls.append(seconds)
        if calls.count("sweep") == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(worker_lease_monitor, "sweep_once", sweep)
    monkeypatch.setattr(worker_lease_monitor.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await worker_lease_monitor.monitor()
    assert calls == ["sweep", 5, "sweep", 5]


async def test_background_sweep_drains_persisted_backlog_without_worker(monkeypatch):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import func, insert, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from support.api_run_scope import seed
    from support.stored_files import longtext_sqlite  # noqa: F401

    from testing_agent.core.errors import AppError
    from testing_agent.models import Base
    from testing_agent.models.api_case_run import ApiCaseRun
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.repositories.worker_task import WorkerTaskRepository
    from testing_agent.schemas.workers import WorkerClaimRequest, WorkerTaskEventRequest
    from testing_agent.services.worker_task import WorkerTaskService

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            await session.run_sync(seed)
            await session.execute(
                insert(ApiCaseRun),
                [
                    {
                        "run_id": f"r{i}",
                        "case_id": "api-case",
                        "collection_id": "collection",
                        "environment_id": "env",
                        "trigger_user_id": "u1",
                        "status": "running",
                    }
                    for i in range(201)
                ],
            )
            await session.execute(
                insert(WorkerTask),
                [
                    {
                        "domain": "api",
                        "task_id": f"q{i}",
                        "run_id": f"r{i}",
                        "task_type": "api_case_debug",
                        "worker_id": "old",
                        "status": "running",
                        "lease_expires_at": datetime.now(UTC) - timedelta(minutes=1),
                    }
                    for i in range(201)
                ],
            )
            session.add(
                ApiCaseRun(
                    run_id="ready-run",
                    case_id="api-case",
                    collection_id="collection",
                    environment_id="env",
                    trigger_user_id="u1",
                    status="pending",
                )
            )
            session.add(
                WorkerTask(
                    domain="api",
                    task_id="ready",
                    run_id="ready-run",
                    task_type="api_case_debug",
                    status="pending",
                )
            )
            await session.commit()
        async with sessions() as session:
            claimed = await WorkerTaskService(WorkerTaskRepository(session)).claim(
                "api", WorkerClaimRequest(workerId="fresh")
            )
            assert claimed["taskId"] == "ready"
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(WorkerTask)
                    .where(WorkerTask.status == "failed")
                )
                == 0
            )
        sizes = []
        original = WorkerTaskService.expire_leases

        async def measured(self, domain):
            result = await original(self, domain)
            if domain == "api":
                sizes.append(result)
            return result

        monkeypatch.setattr(WorkerTaskService, "expire_leases", measured)
        await worker_lease_monitor.sweep_once(sessions)
        assert sizes == [100, 100, 1]
        async with sessions() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(WorkerTask)
                    .where(WorkerTask.status == "failed")
                )
                == 201
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ApiCaseRun)
                    .where(ApiCaseRun.status == "failed")
                )
                == 201
            )
            with pytest.raises(AppError):
                await WorkerTaskService(WorkerTaskRepository(session)).complete(
                    "api", "q0", WorkerTaskEventRequest(workerId="old", status="success")
                )
    finally:
        await engine.dispose()
