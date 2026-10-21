"""Expire abandoned work even when no Worker remains online."""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from testing_agent.db.session import AsyncSessionLocal
from testing_agent.repositories.worker_task import WorkerTaskRepository
from testing_agent.services.worker_task import WorkerTaskService

logger = logging.getLogger(__name__)


async def sweep_once(session_factory=AsyncSessionLocal) -> None:
    from testing_agent.services.integration_lifecycle import lifecycle

    # Every batch has its own session/transaction. A failed domain cannot prevent another
    # queue from recovering; durable expiry timestamps are retried on the next tick.
    for domain in ("ai", "api", "ui", "integration"):
        try:
            for _ in range(5):
                async with session_factory() as session:
                    if domain == "integration":
                        recovered = await lifecycle(session).expire()
                        await session.commit()
                    else:
                        recovered = await WorkerTaskService(
                            WorkerTaskRepository(session)
                        ).expire_leases(domain)
                if recovered != 100:
                    break
                await asyncio.sleep(0)
        except Exception as exc:
            logger.warning(
                "Worker lease sweep failed for %s (%s); retrying next interval",
                domain,
                type(exc).__name__,
            )


async def monitor() -> None:
    while True:
        # Recover persisted expiry immediately after startup, even with no online Worker.
        try:
            await sweep_once()
        except Exception as exc:
            logger.warning(
                "Worker lease sweep failed (%s); retrying next interval", type(exc).__name__
            )
        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app):
    from testing_agent.services.file_cleanup import monitor_files
    from testing_agent.services.ldap_reconcile import monitor_ldap
    from testing_agent.services.sprint_metrics_scheduler import monitor_daily_metrics

    ldap_task = asyncio.create_task(monitor_ldap(AsyncSessionLocal))
    metrics_task = asyncio.create_task(monitor_daily_metrics())
    files_task = asyncio.create_task(monitor_files())
    task = asyncio.create_task(monitor())
    try:
        yield
    finally:
        ldap_task.cancel()
        with suppress(asyncio.CancelledError):
            await ldap_task
        metrics_task.cancel()
        with suppress(asyncio.CancelledError):
            await metrics_task
        files_task.cancel()
        with suppress(asyncio.CancelledError):
            await files_task
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
