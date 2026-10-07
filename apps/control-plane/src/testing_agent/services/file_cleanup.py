"""Bounded periodic cleanup; never logs object URLs or credentials."""

import asyncio
import logging

from testing_agent.core.config import get_settings
from testing_agent.db.session import AsyncSessionLocal
from testing_agent.services.integration_maintenance import IntegrationHistoryMaintenance
from testing_agent.services.integration_observation import IntegrationObservation
from testing_agent.services.stored_file import StoredFileService

logger = logging.getLogger(__name__)


async def monitor_files():
    while True:
        await asyncio.sleep(300)
        settings = get_settings()
        try:
            async with AsyncSessionLocal() as session:
                if settings.s3.enabled:
                    result = await StoredFileService(session, settings.s3).cleanup()
                    if result["failed"]:
                        logger.warning("File cleanup: %s failed; will retry", result["failed"])
                history = await IntegrationHistoryMaintenance(
                    session, settings.integration_execution
                ).compact()
                workers_removed = await IntegrationObservation(session, settings).prune()
                await session.commit()
                logger.info(
                    "Integration history cleanup: compacted=%s backlog=%s workers_removed=%s",
                    history["compacted"],
                    history["backlog"],
                    workers_removed,
                )
        except Exception as exc:
            logger.warning("File cleanup failed (%s); will retry", type(exc).__name__)
