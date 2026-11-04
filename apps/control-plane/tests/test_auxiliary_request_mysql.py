"""Exercise report and order-graph idempotency using real MySQL transactions."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
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
from testing_agent.services import ai_report, test_order_graph
from testing_agent.services.ai_report import TestReportWorkflow as ReportWorkflow
from testing_agent.services.stage_storage import authorization
from testing_agent.services.test_order_graph import TestOrderGraphService as GraphService


async def test_report_and_graph_replay_with_mysql(mysql, monkeypatch):  # noqa: F811
    with mysql.begin() as connection:
        sprint = seed_row(connection, Sprint.__table__)
        order = seed_row(
            connection,
            Order.__table__,
            {
                "project_id": sprint["project_id"],
                "sprint_id": sprint["sprint_id"],
            },
        )
        report = seed_row(
            connection,
            AiGenerateTask.__table__,
            {
                "task_type": "test_report_generate",
                "project_id": sprint["project_id"],
                "sprint_id": sprint["sprint_id"],
                "requirement_id": "",
            },
        )
        graph = seed_row(
            connection,
            AiGenerateTask.__table__,
            {
                "task_type": "test_order_graph",
                "project_id": sprint["project_id"],
                "sprint_id": sprint["sprint_id"],
                "requirement_id": "",
                "order_id": order["order_id"],
            },
        )
    monkeypatch.setattr(ai_report, "require_personal_connection", AsyncMock())
    monkeypatch.setattr(
        test_order_graph,
        "require_personal_connection",
        AsyncMock(return_value=SimpleNamespace(connection_id="llm")),
    )
    monkeypatch.setattr(authorization, "authorize_worker_actor", AsyncMock(return_value="actor"))
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    statements = []
    sa.event.listen(
        engine.sync_engine,
        "before_cursor_execute",
        lambda _c, _u, s, _p, _x, _m: statements.append(s.lower()),
    )
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            repository = AiGenerateTaskRepository(session)
            metrics = SimpleNamespace(get=AsyncMock(return_value={"total": 1}))
            reports = ReportWorkflow(
                repository=repository,
                sprint_daily_metrics_service=metrics,
                ensure_project_access=AsyncMock(),
                owned_run=AsyncMock(),
            )
            report_body = {
                "sprintId": sprint["sprint_id"],
                "snapshotDate": "2026-01-15",
                "connectionId": "llm",
                "requestId": "report-request",
            }
            first = await reports.run_test_report(sprint["project_id"], report_body, "actor")
            assert (await reports.run_test_report(sprint["project_id"], report_body, "actor"))[
                "runId"
            ] == first["runId"]
            assert metrics.get.await_count == 1
            with pytest.raises(AppError):
                await reports.run_test_report(
                    sprint["project_id"], {**report_body, "instruction": "changed"}, "actor"
                )
            await session.rollback()

            order_row = SimpleNamespace(**order)
            orders = SimpleNamespace(
                get_accessible_entity=AsyncMock(return_value=order_row),
                repository=SimpleNamespace(get_order_for_update=AsyncMock(return_value=order_row)),
                ensure_sprint_access=AsyncMock(
                    return_value=SimpleNamespace(project_id=sprint["project_id"])
                ),
            )
            graphs = GraphService(repository, orders, None)
            body = {
                "request_id": "graph-request",
                "connection_id": "llm",
                "graph_input": {
                    "requirements": [],
                    "cases": [{"case_id": "case"}],
                    "case_requirement_links": [],
                },
            }
            generated = await graphs.dispatch("actor", order["order_id"], body)
            assert (await graphs.dispatch("actor", order["order_id"], body))["runId"] == generated[
                "runId"
            ]
            changed = {
                **body,
                "graph_input": {**body["graph_input"], "cases": [{"case_id": "other"}]},
            }
            with pytest.raises(AppError):
                await graphs.dispatch("actor", order["order_id"], changed)
            await session.rollback()
            assert (
                await session.scalar(
                    sa.select(sa.func.count())
                    .select_from(AiExecution)
                    .where(AiExecution.task_id.in_([report["task_id"], graph["task_id"]]))
                )
                == 2
            )
            assert not any("ai_generate_task_runs" in sql for sql in statements)
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(
                sa.delete(WorkerTask).where(
                    WorkerTask.task_id.in_(["report-request", "graph-request"])
                )
            )
            connection.execute(
                sa.delete(AiGenerateTask).where(
                    AiGenerateTask.task_id.in_([report["task_id"], graph["task_id"]])
                )
            )


@pytest.mark.parametrize("kind", ["report", "graph"])
async def test_new_auxiliary_tasks_for_different_objects_run_in_parallel(
    mysql,  # noqa: F811
    monkeypatch,
    kind,
):
    with mysql.begin() as connection:
        first = seed_row(connection, Sprint.__table__)
        second = seed_row(connection, Sprint.__table__, {"project_id": first["project_id"]})
        if kind == "graph":
            objects = [
                seed_row(
                    connection,
                    Order.__table__,
                    {
                        "project_id": first["project_id"],
                        "sprint_id": first["sprint_id"],
                    },
                )
                for _ in range(2)
            ]
        else:
            objects = [first, second]
    monkeypatch.setattr(ai_report, "require_personal_connection", AsyncMock())
    monkeypatch.setattr(
        test_order_graph,
        "require_personal_connection",
        AsyncMock(return_value=SimpleNamespace(connection_id="llm")),
    )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    entered = 0
    ready = asyncio.Event()

    async def start(index, obj):
        nonlocal entered
        async with sessions() as session:
            repository = AiGenerateTaskRepository(session)
            name = (
                "get_task_by_project_sprint_type" if kind == "report" else "get_task_by_order_type"
            )
            lookup = getattr(repository, name)

            async def synchronized_lookup(*args, **kwargs):
                nonlocal entered
                result = await lookup(*args, **kwargs)
                entered += 1
                if entered == 2:
                    ready.set()
                await asyncio.wait_for(ready.wait(), timeout=5)
                return result

            setattr(repository, name, synchronized_lookup)
            if kind == "report":
                service = ReportWorkflow(
                    repository=repository,
                    sprint_daily_metrics_service=SimpleNamespace(get=AsyncMock(return_value={})),
                    ensure_project_access=AsyncMock(),
                    owned_run=AsyncMock(),
                )
                return await service.run_test_report(
                    first["project_id"],
                    {
                        "sprintId": obj["sprint_id"],
                        "snapshotDate": "2026-01-15",
                        "connectionId": "llm",
                        "requestId": f"parallel-{kind}-{index}",
                    },
                    "actor",
                )

            async def lock_order(order_id):
                return await session.scalar(
                    sa.select(Order).where(Order.order_id == order_id).with_for_update()
                )

            orders = SimpleNamespace(
                get_accessible_entity=AsyncMock(return_value=SimpleNamespace(**obj)),
                repository=SimpleNamespace(get_order_for_update=lock_order),
                ensure_sprint_access=AsyncMock(
                    return_value=SimpleNamespace(project_id=first["project_id"])
                ),
            )
            service = GraphService(repository, orders, None)
            return await service.dispatch(
                "actor",
                obj["order_id"],
                {
                    "request_id": f"parallel-{kind}-{index}",
                    "connection_id": "llm",
                    "graph_input": {
                        "requirements": [],
                        "cases": [{"case_id": "case"}],
                        "case_requirement_links": [],
                    },
                },
            )

    identifiers = [f"parallel-{kind}-{index}" for index in range(2)]
    try:
        results = await asyncio.wait_for(
            asyncio.gather(
                *(start(i, obj) for i, obj in enumerate(objects)), return_exceptions=True
            ),
            timeout=15,
        )
        assert not [item for item in results if isinstance(item, BaseException)], results
        assert len({item["runId"] for item in results}) == 2
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(sa.delete(WorkerTask).where(WorkerTask.task_id.in_(identifiers)))
            connection.execute(
                sa.delete(AiGenerateTask).where(
                    AiGenerateTask.project_id == first["project_id"],
                    AiGenerateTask.task_type
                    == ("test_report_generate" if kind == "report" else "test_order_graph"),
                )
            )


@pytest.mark.parametrize("kind", ["report", "graph"])
async def test_same_auxiliary_request_is_idempotent_during_concurrent_first_launch(
    mysql,  # noqa: F811
    monkeypatch,
    kind,
):
    with mysql.begin() as connection:
        sprint = seed_row(connection, Sprint.__table__)
        order = seed_row(
            connection,
            Order.__table__,
            {
                "project_id": sprint["project_id"],
                "sprint_id": sprint["sprint_id"],
            },
        )
    monkeypatch.setattr(ai_report, "require_personal_connection", AsyncMock())
    monkeypatch.setattr(
        test_order_graph,
        "require_personal_connection",
        AsyncMock(return_value=SimpleNamespace(connection_id="llm")),
    )
    monkeypatch.setattr(authorization, "authorize_worker_actor", AsyncMock(return_value="actor"))
    metrics = SimpleNamespace(get=AsyncMock(return_value={}))
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    identity = f"same-{kind}-request"

    async def start():
        async with sessions() as session:
            repository = AiGenerateTaskRepository(session)
            if kind == "report":
                service = ReportWorkflow(
                    repository=repository,
                    sprint_daily_metrics_service=metrics,
                    ensure_project_access=AsyncMock(),
                    owned_run=AsyncMock(),
                )
                return await service.run_test_report(
                    sprint["project_id"],
                    {
                        "sprintId": sprint["sprint_id"],
                        "snapshotDate": "2026-01-15",
                        "connectionId": "llm",
                        "requestId": identity,
                    },
                    "actor",
                )

            async def lock_order(order_id):
                return await session.scalar(
                    sa.select(Order).where(Order.order_id == order_id).with_for_update()
                )

            orders = SimpleNamespace(
                get_accessible_entity=AsyncMock(return_value=SimpleNamespace(**order)),
                repository=SimpleNamespace(get_order_for_update=lock_order),
                ensure_sprint_access=AsyncMock(
                    return_value=SimpleNamespace(project_id=sprint["project_id"])
                ),
            )
            return await GraphService(repository, orders, None).dispatch(
                "actor",
                order["order_id"],
                {
                    "request_id": identity,
                    "connection_id": "llm",
                    "graph_input": {
                        "requirements": [],
                        "cases": [{"case_id": "case"}],
                        "case_requirement_links": [],
                    },
                },
            )

    try:
        results = await asyncio.wait_for(
            asyncio.gather(start(), start(), return_exceptions=True), timeout=15
        )
        assert not [item for item in results if isinstance(item, BaseException)], results
        assert results[0]["runId"] == results[1]["runId"]
        if kind == "report":
            assert metrics.get.await_count == 1
        async with sessions() as session:
            assert (
                await session.scalar(
                    sa.select(sa.func.count())
                    .select_from(AiExecution)
                    .join(AiGenerateTask, AiGenerateTask.task_id == AiExecution.task_id)
                    .where(AiGenerateTask.project_id == sprint["project_id"])
                )
                == 1
            )
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(sa.delete(WorkerTask).where(WorkerTask.task_id == identity))
            connection.execute(
                sa.delete(AiGenerateTask).where(AiGenerateTask.project_id == sprint["project_id"])
            )
