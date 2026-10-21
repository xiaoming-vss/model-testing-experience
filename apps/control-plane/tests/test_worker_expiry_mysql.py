"""Expiry discovery must not hold MySQL secondary-index range locks."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql as mysql

from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.worker_task import WorkerTaskRepository


async def test_expiry_skips_competing_sweeper_and_does_not_block_heartbeats(mysql):
    now = datetime.now(UTC)
    with mysql.begin() as connection:
        connection.execute(
            WorkerTask.__table__.insert(),
            [
                {
                    "domain": "api",
                    "task_id": f"expire-{i}",
                    "task_type": "api_case_debug",
                    "run_id": f"r{i}",
                    "status": "running",
                    "lease_expires_at": now + timedelta(hours=1)
                    if i == 0
                    else now - timedelta(minutes=1),
                }
                for i in range(211)
            ],
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as first, sessions() as second:
            left = await WorkerTaskRepository(first).expired_tasks("api")
            right = await asyncio.wait_for(WorkerTaskRepository(second).expired_tasks("api"), 2)
            assert len(left) == len(right) == 100
            assert not {row.task_id for row in left} & {row.task_id for row in right}

            async def heartbeat():
                async with sessions() as live:
                    await live.execute(
                        update(WorkerTask)
                        .where(WorkerTask.domain == "api", WorkerTask.task_id == "expire-0")
                        .values(lease_expires_at=now + timedelta(hours=2))
                    )
                    await live.commit()

            await asyncio.wait_for(heartbeat(), 2)
            for task in left + right:
                task.status = "failed"
            await first.commit()
            await second.commit()
        async with sessions() as last:
            assert len(await WorkerTaskRepository(last).expired_tasks("api")) == 10
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(WorkerTask.__table__.delete())


async def test_renewed_candidate_is_rechecked_under_lock(mysql):
    now = datetime.now(UTC)
    with mysql.begin() as connection:
        connection.execute(
            WorkerTask.__table__.insert().values(
                domain="api",
                task_id="renewed",
                task_type="api_case_debug",
                run_id="r",
                status="running",
                lease_expires_at=now - timedelta(minutes=1),
            )
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as reader:
            original = reader.scalars

            discovered = False

            async def discover(statement):
                nonlocal discovered
                result = await original(statement)
                if discovered:
                    return result
                discovered = True
                async with sessions() as heartbeat:
                    await heartbeat.execute(
                        update(WorkerTask)
                        .where(WorkerTask.domain == "api", WorkerTask.task_id == "renewed")
                        .values(lease_expires_at=now + timedelta(minutes=1))
                    )
                    await heartbeat.commit()
                return result

            reader.scalars = discover
            assert await WorkerTaskRepository(reader).expired_tasks("api") == []
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(WorkerTask.__table__.delete())


def test_expiry_discovery_uses_compound_lease_index(mysql):
    now = datetime.now(UTC)
    with mysql.begin() as connection:
        connection.execute(
            WorkerTask.__table__.insert(),
            [
                {
                    "domain": "api",
                    "task_id": f"plan-{i}",
                    "task_type": "api_case_debug",
                    "run_id": f"r{i}",
                    "status": "running",
                    "lease_expires_at": now + timedelta(hours=1)
                    if i > 9
                    else now - timedelta(minutes=1),
                }
                for i in range(5000)
            ],
        )
        query = (
            select(WorkerTask.id)
            .where(
                WorkerTask.domain == "api",
                WorkerTask.status.in_(["claimed", "running"]),
                WorkerTask.lease_expires_at <= now,
            )
            .order_by(WorkerTask.lease_expires_at, WorkerTask.id)
            .limit(500)
        )
        compiled = str(query.compile(dialect=mysql.dialect, compile_kwargs={"literal_binds": True}))
        plan = json.loads(
            connection.exec_driver_sql("EXPLAIN FORMAT=JSON " + compiled).scalar_one()
        )
        assert '"key": "idx_worker_domain_lease"' in json.dumps(plan)
        connection.execute(WorkerTask.__table__.delete())
