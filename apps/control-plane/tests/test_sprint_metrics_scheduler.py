from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from testing_agent.db.base import Base
from testing_agent.models.project import Project
from testing_agent.models.sprint import Sprint
from testing_agent.models.sprint_daily_metrics import SprintDailyMetrics
from testing_agent.repositories.sprint_daily_metrics import SprintDailyMetricsRepository
from testing_agent.services.sprint_daily_metrics import SprintDailyMetricsService
from testing_agent.services.sprint_metrics_scheduler import due_today, sweep_daily_metrics


def test_schedule_uses_beijing_day_and_does_not_backfill_previous_days():
    assert due_today(datetime(2026, 10, 13, 15, 54, tzinfo=UTC)) is None
    due = due_today(datetime(2026, 10, 13, 15, 55, tzinfo=UTC))
    assert due.isoformat() == "2026-10-13T23:55:00+08:00"
    assert due_today(datetime(2026, 10, 13, 16, 0, tzinfo=UTC)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_first", [False, True])
async def test_collects_only_running_sprints_once_and_preserves_manual_history(
    monkeypatch, fail_first
):
    engine = create_async_engine("sqlite+aiosqlite://")
    now = datetime(2026, 10, 13, 15, 56, tzinfo=UTC)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(
                c, tables=[Project.__table__, Sprint.__table__, SprintDailyMetrics.__table__]
            )
        )
    async with factory() as session:
        session.add(Project(project_id="p", user_id="u", name="项目"))
        for key, start, end in [
            ("running", now - timedelta(days=2), now + timedelta(days=1)),
            ("running2", now - timedelta(days=2), now + timedelta(days=1)),
            ("finished", now - timedelta(days=2), now),
            ("future", now + timedelta(days=1), now + timedelta(days=2)),
        ]:
            session.add(
                Sprint(sprint_id=key, project_id="p", name=key, start_time=start, end_time=end)
            )
        session.add(
            SprintDailyMetrics(
                project_id="p",
                sprint_id="running",
                snapshot_date=now.date() - timedelta(days=1),
                function_case_total=9,
            )
        )
        await session.commit()
    failed = False

    async def apply_metrics(actor, sprint, metric):
        nonlocal failed
        if fail_first and sprint.sprint_id == "running" and not failed:
            failed = True
            raise RuntimeError("simulated transient collection failure")
        metric.function_case_total = 12

    collect = AsyncMock(side_effect=apply_metrics)
    monkeypatch.setattr(SprintDailyMetricsService, "apply_snapshot_metrics", collect)
    try:
        assert await sweep_daily_metrics(now - timedelta(minutes=2), factory) == 0
        assert await sweep_daily_metrics(now, factory) == (1 if fail_first else 2)
        assert await sweep_daily_metrics(now + timedelta(minutes=1), factory) == (
            1 if fail_first else 0
        )
        assert await sweep_daily_metrics(now + timedelta(minutes=2), factory) == 0
        assert collect.await_count == (3 if fail_first else 2)
        async with factory() as session:
            repo = SprintDailyMetricsRepository(session)
            rows = await repo.list("running")
            assert len(rows) == 2
            assert rows[0].function_case_total == 9
            assert rows[1].function_case_total == 12
            assert len(await repo.list("running2")) == 1
            assert await repo.list("finished") == []
            assert await repo.list("future") == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_daily_monitor_starts_and_stops_with_application(monkeypatch):
    import asyncio

    from testing_agent.services import file_cleanup, sprint_metrics_scheduler, worker_lease_monitor

    started, stopped = asyncio.Event(), asyncio.Event()

    async def daily_monitor():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    async def idle():
        await asyncio.Event().wait()

    monkeypatch.setattr(sprint_metrics_scheduler, "monitor_daily_metrics", daily_monitor)
    monkeypatch.setattr(worker_lease_monitor, "monitor", idle)
    monkeypatch.setattr(file_cleanup, "monitor_files", idle)
    async with worker_lease_monitor.lifespan(None):
        await asyncio.wait_for(started.wait(), 1)
    assert stopped.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["collection", "sweep"])
async def test_monitor_logs_safe_error_traceback(monkeypatch, caplog, failure_stage):
    import asyncio
    import logging

    from testing_agent.services import sprint_metrics_scheduler as scheduler

    secret = "password=do-not-log-this"

    async def fail(*args):
        raise RuntimeError(secret)

    async def stop_after_tick(*args):
        raise asyncio.CancelledError

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(scheduler.asyncio, "sleep", stop_after_tick)
    if failure_stage == "collection":
        monkeypatch.setattr(
            SprintDailyMetricsRepository, "list_running_sprint_ids", AsyncMock(return_value=["s1"])
        )
        monkeypatch.setattr(SprintDailyMetricsService, "collect_scheduled", fail)
        original_sweep = scheduler.sweep_daily_metrics

        async def sweep():
            return await original_sweep(datetime(2026, 10, 13, 15, 56, tzinfo=UTC), Session)

        monkeypatch.setattr(scheduler, "sweep_daily_metrics", sweep)
    else:
        monkeypatch.setattr(scheduler, "sweep_daily_metrics", fail)
    with caplog.at_level(logging.ERROR), pytest.raises(asyncio.CancelledError):
        await scheduler.monitor_daily_metrics()
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelno == logging.ERROR
    assert record.error_type == "RuntimeError"
    assert "fail" in record.stack_trace
    assert "test_sprint_metrics_scheduler.py" in record.stack_trace
    if failure_stage == "collection":
        assert record.sprint_id == "s1"
    assert secret not in str(record.__dict__)
