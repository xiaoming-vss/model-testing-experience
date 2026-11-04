"""Concurrent report dispatch uses the iteration lock, even on first creation."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.core.errors import AppError
from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.sprint import Sprint
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.ai_report import TestReportWorkflow


async def test_concurrent_report_dispatch_creates_only_one_run(mysql, monkeypatch):  # noqa: F811
    with mysql.begin() as connection:
        sprint = seed_row(connection, Sprint.__table__)
    monkeypatch.setattr(
        "testing_agent.services.ai_report.require_personal_connection", AsyncMock(return_value=None)
    )

    async def metrics(*args):
        await asyncio.sleep(0.1)
        return {"function": {"total": 1}}

    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    statements = []
    sa.event.listen(
        engine.sync_engine,
        "before_cursor_execute",
        lambda _c, _u, sql, _p, _x, _m: statements.append(sql.lower()),
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    body = {"sprintId": sprint["sprint_id"], "connectionId": "llm", "snapshotDate": "2026-01-15"}

    async def dispatch():
        async with sessions() as session:
            repository = AiGenerateTaskRepository(session)
            workflow = TestReportWorkflow(
                repository=repository,
                sprint_daily_metrics_service=SimpleNamespace(get=metrics),
                ensure_project_access=AsyncMock(),
                owned_run=AsyncMock(),
            )
            try:
                return await workflow.run_test_report(sprint["project_id"], body, "user")
            except AppError:
                await session.rollback()
                return None

    try:
        results = await asyncio.wait_for(asyncio.gather(dispatch(), dispatch()), timeout=15)
        assert sum(result is not None for result in results) == 1
        assert not any("ai_generate_task_runs" in statement for statement in statements)
        async with sessions() as session:
            count = await session.scalar(
                sa.select(sa.func.count())
                .select_from(AiExecution)
                .join(AiGenerateTask, AiGenerateTask.task_id == AiExecution.task_id)
                .where(AiGenerateTask.sprint_id == sprint["sprint_id"])
            )
            assert count == 1
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(
                sa.delete(WorkerTask).where(WorkerTask.task_type == "test_report_generate")
            )
            connection.execute(
                sa.delete(AiGenerateTask).where(AiGenerateTask.sprint_id == sprint["sprint_id"])
            )
