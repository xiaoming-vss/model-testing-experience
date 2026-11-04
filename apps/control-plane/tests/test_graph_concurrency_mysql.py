"""Concurrent graph dispatch is serialized by its test-order row."""

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
from testing_agent.models.test_order import TestOrder as Order
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.test_order import TestOrderRepository
from testing_agent.repositories.test_order_entry import TestOrderEntryRepository
from testing_agent.services.test_order import TestOrderService as OrderService
from testing_agent.services.test_order_graph import TestOrderGraphService as GraphService


async def test_concurrent_first_graph_dispatch_creates_one_run(mysql, monkeypatch):  # noqa: F811
    with mysql.begin() as connection:
        sprint = seed_row(connection, Sprint.__table__)
        order = seed_row(
            connection,
            Order.__table__,
            {"project_id": sprint["project_id"], "sprint_id": sprint["sprint_id"]},
        )
    monkeypatch.setattr("testing_agent.services.test_order.require_project_access", AsyncMock())
    monkeypatch.setattr(
        "testing_agent.services.test_order_graph.require_personal_connection",
        AsyncMock(return_value=SimpleNamespace(connection_id="llm")),
    )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    statements = []
    sa.event.listen(
        engine.sync_engine,
        "before_cursor_execute",
        lambda _c, _u, sql, _p, _x, _m: statements.append(sql.lower()),
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    body = {
        "graph_input": {
            "requirements": [],
            "cases": [{"case_id": "case"}],
            "case_requirement_links": [],
        },
        "connection_id": "llm",
    }

    async def dispatch():
        async with sessions() as session:
            entries = TestOrderEntryRepository(session)
            orders = OrderService(TestOrderRepository(session), entries)
            service = GraphService(AiGenerateTaskRepository(session), orders, entries)
            try:
                return await service.dispatch("user", order["order_id"], body)
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
                .where(AiGenerateTask.order_id == order["order_id"])
            )
            assert count == 1
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(
                sa.delete(WorkerTask).where(WorkerTask.task_type == "test_order_graph")
            )
            connection.execute(
                sa.delete(AiGenerateTask).where(AiGenerateTask.order_id == order["order_id"])
            )
