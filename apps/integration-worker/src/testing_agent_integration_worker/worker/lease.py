import asyncio
import logging
import time

from testing_agent_integration_worker.core.errors import ControlPlaneError

logger = logging.getLogger(__name__)


async def maintain_lease(control_plane, execution, interval, progress) -> None:
    interval = min(interval, execution.claim.lease_seconds / 3)
    while execution.window.alive():
        await asyncio.sleep(interval)
        started = time.monotonic()
        try:
            seconds = await control_plane.heartbeat(
                execution.claim.job_id, execution.claim.identity()
            )
            progress()
            if not execution.window.renew(started, seconds):
                return
        except ControlPlaneError as error:
            progress()
            logger.warning("Lease lost job=%s status=%s", execution.claim.job_id, error.status)
            execution.window.lost = True
            execution.window.stopped = True
            return
