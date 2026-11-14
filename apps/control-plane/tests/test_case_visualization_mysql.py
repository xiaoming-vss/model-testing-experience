"""Real MySQL lock and cleanup invariants on a disposable test database."""

import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.core.errors import AppError
from testing_agent.models import (
    AiGenerateTask,
    AiGenerationAttempt,
    Project,
    Sprint,
    User,
    WorkerTask,
)
from testing_agent.models.test_order import TestOrder as Order
from testing_agent.models.test_order_entry import TestOrderEntry as Entry
from testing_agent.repositories.case_visualization import CaseVisualizationRepository
from testing_agent.repositories.test_order import TestOrderRepository
from testing_agent.repositories.test_order_entry import TestOrderEntryRepository
from testing_agent.schemas.workers import WorkerClaimRequest, WorkerTaskEventRequest
from testing_agent.services.resource_deletion import SqlResourceDeletion
from testing_agent.services.stage_storage.worker_service import DirectStageWorkerService
from testing_agent.services.test_order import TestOrderService as OrderService
from testing_agent.services.test_order_case_visualization import (
    TestOrderCaseVisualizationService as VisualService,
)
from testing_agent.services.worker import find_task

EXAMPLE = json.loads(
    (
        Path(__file__).parents[1]
        / "default-skills/mtx-analyze-case-visualization/references/examples.json"
    ).read_text()
)[0]


def seeded(database):
    with database.begin() as connection:
        sprint = seed_row(connection, Sprint.__table__)
        order = seed_row(
            connection,
            Order.__table__,
            {"project_id": sprint["project_id"], "sprint_id": sprint["sprint_id"]},
        )
        entry = seed_row(
            connection,
            Entry.__table__,
            {
                "order_id": order["order_id"],
                "snapshot_json": EXAMPLE["input"]["content"],
                "case_type": "function",
            },
        )
        actor = connection.scalar(
            sa.select(Project.user_id).where(Project.project_id == order["project_id"])
        )
        seed_row(connection, User.__table__, {"user_id": actor})
    return order["order_id"], entry["entry_id"], actor


def mocks(monkeypatch):
    monkeypatch.setattr("testing_agent.services.test_order.require_project_access", AsyncMock())
    monkeypatch.setattr(
        "testing_agent.services.test_order_case_visualization.require_personal_connection",
        AsyncMock(return_value=SimpleNamespace(connection_id="llm")),
    )
    monkeypatch.setattr(
        "testing_agent.services.stage_storage.authorization.require_personal_connection",
        AsyncMock(return_value=SimpleNamespace(connection_id="llm")),
    )


def service(session):
    return VisualService(
        CaseVisualizationRepository(session),
        OrderService(TestOrderRepository(session), TestOrderEntryRepository(session)),
    )


@pytest.mark.parametrize("race", range(3))
async def test_concurrent_dispatch_and_completion_delete(mysql, monkeypatch, race):  # noqa: F811
    mocks(monkeypatch)
    order, entry, actor = seeded(mysql)
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def dispatch(req):
        async with sessions() as session:
            return await service(session).dispatch(
                actor, order, entry, {"request_id": req, "connection_id": "llm", "mode": "generate"}
            )

    try:
        results = await asyncio.wait_for(asyncio.gather(dispatch("one"), dispatch("two")), 15)
        assert {r["disposition"] for r in results} == {"queued", "existing_active"}
        assert results[0]["runId"] == results[1]["runId"]
        async with sessions() as session:
            attempt = await session.scalar(
                sa.select(AiGenerationAttempt).where(
                    AiGenerationAttempt.execution_id == results[0]["runId"]
                )
            )
            worker = await find_task(session, "ai", attempt.worker_task_id)
            worker_id, attempt_id = worker.task_id, attempt.id
            await DirectStageWorkerService(session).claim(
                worker, WorkerClaimRequest(worker_id="worker")
            )
        output = copy.deepcopy(EXAMPLE["output"])
        output["executionEntryId"] = entry

        async def complete():
            async with sessions() as session:
                try:
                    worker = await find_task(session, "ai", worker_id)
                    await DirectStageWorkerService(session).complete(
                        worker,
                        WorkerTaskEventRequest(
                            worker_id="worker",
                            run_id=attempt_id,
                            status="success",
                            result_yaml=json.dumps(output),
                        ),
                    )
                except AppError:
                    await (
                        session.rollback()
                    )  # Deletion may win; late completion must not revive data.

        async def delete():
            async with sessions() as session:
                row = await session.scalar(sa.select(Entry).where(Entry.entry_id == entry))
                await SqlResourceDeletion().delete(session, row)
                await session.commit()

        await asyncio.wait_for(asyncio.gather(complete(), delete()), 15)
        async with sessions() as session:
            assert await session.scalar(sa.select(Entry).where(Entry.entry_id == entry)) is None
            assert (
                await session.scalar(
                    sa.select(AiGenerateTask).where(AiGenerateTask.order_id == order)
                )
                is None
            )
            assert (
                await session.scalar(sa.select(WorkerTask).where(WorkerTask.task_id == worker_id))
                is None
            )
    finally:
        await engine.dispose()


def test_visualization_migration_roundtrip(mysql):  # noqa: F811
    from support.initial_schema_migration import assert_current_schema, migration_config

    from alembic import command

    with mysql.connect() as connection:
        config = migration_config(connection)
        assert_current_schema(connection)
        command.downgrade(config, "20261113_0002")
        assert "test_order_entry_visualizations" not in sa.inspect(connection).get_table_names()
        command.upgrade(config, "head")
        assert_current_schema(connection)
        connection.commit()
