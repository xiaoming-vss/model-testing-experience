"""Expire abandoned work even when no Worker remains online."""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from testing_agent.db.session import AsyncSessionLocal
from testing_agent.repositories.worker_task import WorkerTaskRepository
from testing_agent.services.worker_task import WorkerTaskService

logger = logging.getLogger(__name__)


async def sweep_once(session_factory=AsyncSessionLocal):
    for domain in ("ai", "api", "ui"):
        async with session_factory() as session:
            await WorkerTaskService(WorkerTaskRepository(session)).expire_leases(domain)
    from testing_agent.services.integration_lifecycle import lifecycle

    async with session_factory() as session:
        await lifecycle(session).expire()
        await session.commit()


async def monitor():
    while True:
        await asyncio.sleep(5)
        try:
            await sweep_once()
        except Exception as exc:
            # Do not log SQL parameters, snapshots or credentials.
            logger.warning(
                "Worker lease sweep failed (%s); retrying next interval", type(exc).__name__
            )


@asynccontextmanager
async def lifespan(app):
    from testing_agent.services.file_cleanup import monitor_files

    files_task = asyncio.create_task(monitor_files())
    task = asyncio.create_task(monitor())
    try:
        yield
    finally:
        files_task.cancel()
        with suppress(asyncio.CancelledError):
            await files_task
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
