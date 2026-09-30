"""Bounded periodic cleanup; never logs object URLs or credentials."""

import asyncio
import logging

from testing_agent.core.config import get_settings
from testing_agent.db.session import AsyncSessionLocal
from testing_agent.services.stored_file import StoredFileService

logger = logging.getLogger(__name__)


async def monitor_files():
    while True:
        await asyncio.sleep(300)
        settings = get_settings().s3
        if not settings.enabled:
            continue
        try:
            async with AsyncSessionLocal() as session:
                result = await StoredFileService(session, settings).cleanup()
                if result["failed"]:
                    logger.warning("File cleanup: %s failed; will retry", result["failed"])
        except Exception as exc:
            logger.warning("File cleanup failed (%s); will retry", type(exc).__name__)
