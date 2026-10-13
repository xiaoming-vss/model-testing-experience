"""Collect local metrics at 23:55 Asia/Shanghai for currently running sprints."""

import asyncio
import logging
import traceback
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from testing_agent.db.session import AsyncSessionLocal
from testing_agent.repositories.sprint_daily_metrics import SprintDailyMetricsRepository
from testing_agent.services.sprint_daily_metrics import SprintDailyMetricsService

logger = logging.getLogger(__name__)
BUSINESS_TIMEZONE = ZoneInfo("Asia/Shanghai")


def due_today(now: datetime) -> datetime | None:
    local = now.astimezone(BUSINESS_TIMEZONE)
    due = local.replace(hour=23, minute=55, second=0, microsecond=0)
    return due if local >= due else None


async def sweep_daily_metrics(
    now: datetime | None = None,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
) -> int:
    now = now or datetime.now(UTC)
    due = due_today(now)
    if due is None:
        return 0
    async with session_factory() as session:
        ids = await SprintDailyMetricsRepository(session).list_running_sprint_ids(now)
    collected = 0
    for sprint_id in ids:
        # Each sprint owns a separate transaction; failed collections retry on the
        # next tick, while row locks + updated_at prevent duplicate daily writes.
        try:
            async with session_factory() as session:
                service = SprintDailyMetricsService(SprintDailyMetricsRepository(session))
                if await service.collect_scheduled(sprint_id, now, due):
                    collected += 1
        except Exception as exc:
            _log_failure("Daily metrics collection failed", exc, sprint_id=sprint_id)
    if collected:
        logger.info("Daily metrics collected: snapshot_date=%s count=%s", due.date(), collected)
    return collected


async def monitor_daily_metrics() -> None:
    while True:
        try:
            await sweep_daily_metrics()
        except Exception as exc:
            _log_failure("Daily metrics sweep failed", exc)
        await asyncio.sleep(60)


def _log_failure(event: str, exc: Exception, *, sprint_id: str | None = None) -> None:
    # Do not retain exception messages, SQL parameters, source lines or frame locals.
    stack_trace = "\n".join(
        f"{frame.f_code.co_filename}:{lineno} in {frame.f_code.co_name}"
        for frame, lineno in traceback.walk_tb(exc.__traceback__)
    )
    fields: dict[str, str] = {"error_type": type(exc).__name__, "stack_trace": stack_trace}
    if sprint_id is not None:
        fields["sprint_id"] = sprint_id
    logger.error("%s: %s\n%s", event, type(exc).__name__, stack_trace, extra=fields)
