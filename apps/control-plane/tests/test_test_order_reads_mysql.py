"""MySQL pagination, JSON backfill and stable entry ordering."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.initial_schema_migration import migration_config
from support.mysql_initialization import mysql as mysql
from support.mysql_initialization import seed_row

from alembic import command
from testing_agent.domain.test_order_query import EntryQuery
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.requirement import Requirement
from testing_agent.models.test_order import TestOrder as Order
from testing_agent.models.test_order_entry import TestOrderEntry as Entry
from testing_agent.repositories.test_order import TestOrderRepository as OrderRepository
from testing_agent.repositories.test_order_reads import TestOrderReadRepository as EntryRepository


@pytest.mark.asyncio
async def test_mysql_backfill_and_read_windows(mysql):
    body = {
        "preconditions": [],
        "steps": [{"action": "a", "expected": "b"}, {"action": "c", "expected": "d"}],
    }
    with mysql.begin() as connection:
        order = seed_row(connection, Order.__table__)
        requirement = seed_row(connection, Requirement.__table__, {"sprint_id": order["sprint_id"]})
        suite = seed_row(
            connection,
            FunctionTestSuite.__table__,
            {"requirement_id": requirement["requirement_id"]},
        )
        connection.execute(
            FunctionTestCase.__table__.insert(),
            [
                {
                    "case_id": f"mysql-window-{i}",
                    "suite_id": suite["suite_id"],
                    "title": f"case {i}",
                    "module": "50%_done" if i == 29 else "normal",
                    "content_json": body,
                }
                for i in range(30)
            ],
        )
        connection.execute(
            Entry.__table__.insert(),
            [
                {
                    "entry_id": f"mysql-entry-{i}",
                    "order_id": order["order_id"],
                    "case_id": f"mysql-window-{i}",
                    "order_no": i // 2,
                    "status": "passed" if i < 25 else "pending",
                    "snapshot_json": body,
                    "step_count": 0,
                    "assignee_user_id": "actor" if i % 2 == 0 else "",
                }
                for i in range(30)
            ],
        )
    with mysql.connect() as connection:
        config = migration_config(connection)
        command.downgrade(config, "20261021_0047")
        connection.commit()
        command.upgrade(config, "head")
        connection.commit()
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            reader = EntryRepository(session)
            first = await reader.page(order["order_id"], "actor", EntryQuery())
            assert first["total"] == 30 and first["mineCount"] == 15
            assert len(first["items"]) == 20
            assert all(row["step_count"] == 2 and "snapshot" not in row for row in first["items"])
            resumed = await reader.page(order["order_id"], "actor", EntryQuery(resume=True))
            assert resumed["page"] == 2 and resumed["preferredEntryId"] == "mysql-entry-25"
            focused = await reader.page(
                order["order_id"], "actor", EntryQuery(focus_entry_id="mysql-entry-29")
            )
            assert focused["page"] == 2 and focused["preferredEntryId"] == "mysql-entry-29"
            literal = await reader.page(order["order_id"], "actor", EntryQuery(keyword="%_"))
            assert literal["total"] == 1
            assert (await reader.detail(order["order_id"], "mysql-entry-29"))["snapshot"] == body
            orders, total, page = await OrderRepository(session).page_by_project(
                order["project_id"], sprint_id=order["sprint_id"], keyword="", page=1, page_size=20
            )
            assert total == 1 and page == 1 and orders[0].entries_total == 30
            assert (await session.scalars(select(Entry.step_count))).all() == [2] * 30
    finally:
        await engine.dispose()
