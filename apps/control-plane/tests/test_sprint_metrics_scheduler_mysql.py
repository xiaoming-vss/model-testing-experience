"""Actual row-lock serialization against an explicitly disposable MySQL database."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql as mysql

from testing_agent.models.project import Project
from testing_agent.models.sprint import Sprint
from testing_agent.models.sprint_daily_metrics import SprintDailyMetrics
from testing_agent.models.user import User
from testing_agent.repositories.sprint_daily_metrics import SprintDailyMetricsRepository
from testing_agent.services.sprint_daily_metrics import SprintDailyMetricsService
from testing_agent.services.sprint_metrics_scheduler import due_today


async def test_concurrent_collectors_commit_one_daily_snapshot(mysql, monkeypatch):
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    prefix = uuid4().hex
    now = datetime(2026, 10, 13, 15, 56, tzinfo=UTC)
    due = due_today(now)
    entered, release, second_lock_attempted = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls = 0
    original_apply = SprintDailyMetricsService.apply_snapshot_metrics
    original_lock = SprintDailyMetricsRepository.lock_sprint

    async def hold_collection(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        await original_apply(self, *args, **kwargs)

    async def observe_lock(self, sprint_id):
        if entered.is_set():
            second_lock_attempted.set()
        return await original_lock(self, sprint_id)

    monkeypatch.setattr(SprintDailyMetricsService, "apply_snapshot_metrics", hold_collection)
    monkeypatch.setattr(SprintDailyMetricsRepository, "lock_sprint", observe_lock)

    async def collect():
        async with sessions() as session:
            return await SprintDailyMetricsService(
                SprintDailyMetricsRepository(session)
            ).collect_scheduled(prefix, now, due)

    try:
        async with sessions() as session:
            session.add(User(user_id=prefix, nickname=prefix))
            await session.flush()
            session.add(Project(project_id=prefix, user_id=prefix, name=prefix))
            await session.flush()
            session.add(
                Sprint(
                    sprint_id=prefix,
                    project_id=prefix,
                    name=prefix,
                    start_time=now - timedelta(days=1),
                    end_time=now + timedelta(days=1),
                )
            )
            await session.commit()
        async with asyncio.TaskGroup() as group:
            first = group.create_task(collect())
            await asyncio.wait_for(entered.wait(), 5)
            second = group.create_task(collect())
            await asyncio.wait_for(second_lock_attempted.wait(), 5)
            release.set()
        assert sorted([first.result(), second.result()]) == [False, True]
        assert calls == 1
        async with sessions() as session:
            rows = (
                await session.scalars(
                    select(SprintDailyMetrics).where(SprintDailyMetrics.sprint_id == prefix)
                )
            ).all()
            assert len(rows) == 1
            assert rows[0].snapshot_date == due.date()
            assert rows[0].bug_metrics_collected is True
    finally:
        async with sessions() as session:
            for model, predicate in (
                (SprintDailyMetrics, SprintDailyMetrics.sprint_id == prefix),
                (Sprint, Sprint.sprint_id == prefix),
                (Project, Project.project_id == prefix),
                (User, User.user_id == prefix),
            ):
                await session.execute(delete(model).where(predicate))
            await session.commit()
        await engine.dispose()
