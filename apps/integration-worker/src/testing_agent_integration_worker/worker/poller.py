import asyncio
import logging
import os
import socket
import time
from contextlib import suppress
from uuid import uuid4

from testing_agent_integration_worker.core.errors import ControlPlaneError
from testing_agent_integration_worker.domain.execution import Execution, ExecutionWindow
from testing_agent_integration_worker.worker.lease import maintain_lease

logger = logging.getLogger(__name__)


class Poller:
    def __init__(self, control_plane, handler, step_execution, settings, health):
        self.control_plane, self.handler, self.steps = control_plane, handler, step_execution
        self.settings, self.health = settings, health
        self.worker_id = f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:12]}"
        self.stop_event = asyncio.Event()
        self.execution: Execution | None = None
        self.active_task: asyncio.Task | None = None

    def stop(self) -> None:
        self.stop_event.set()
        if self.execution is not None:
            self.execution.window.stopped = True

    async def pause(self, seconds: float) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(self.stop_event.wait(), timeout=seconds)

    async def execute(self, claim, started):
        window = ExecutionWindow(
            started + claim.lease_seconds - self.settings.lease_margin_seconds,
            margin=self.settings.lease_margin_seconds,
        )
        self.execution = Execution(claim, window)
        heartbeat = asyncio.create_task(
            maintain_lease(
                self.control_plane,
                self.execution,
                self.settings.heartbeat_interval_seconds,
                self.health.progress,
            )
        )
        try:
            if window.active():
                await self.handler.handle(self.execution)
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
            self.execution = None
            self.health.progress()

    async def run(self) -> None:
        pending_request = uuid4().hex
        pending_started: float | None = None
        backoff = self.settings.poll_interval_seconds
        self.health.progress()
        try:
            while not self.stop_event.is_set():
                try:
                    await self.steps.replay_evidence()
                    if pending_started is None:
                        pending_started = time.monotonic()
                    response = await self.control_plane.claim(self.worker_id, pending_request)
                    self.health.progress()
                    started = pending_started
                    pending_request, pending_started = uuid4().hex, None
                    backoff = self.settings.poll_interval_seconds
                    if response.job is None:
                        await self.pause(self.settings.poll_interval_seconds)
                        continue
                    self.active_task = asyncio.create_task(self.execute(response.job, started))
                    stop = asyncio.create_task(self.stop_event.wait())
                    try:
                        done, _ = await asyncio.wait(
                            {self.active_task, stop}, return_when=asyncio.FIRST_COMPLETED
                        )
                        if stop in done:
                            if self.execution is not None:
                                self.execution.window.stopped = True
                            await asyncio.wait_for(
                                self.active_task, timeout=self.settings.shutdown_grace_seconds
                            )
                        else:
                            await self.active_task
                    finally:
                        stop.cancel()
                        with suppress(asyncio.CancelledError):
                            await stop
                        self.active_task = None
                except ControlPlaneError as error:
                    self.health.progress()
                    logger.warning(
                        "Control-plane unavailable worker=%s status=%s",
                        self.worker_id,
                        error.status,
                    )
                    await self.pause(backoff)
                    backoff = min(30, backoff * 2)
                except Exception as error:
                    self.health.progress()
                    logger.warning(
                        "Job stopped worker=%s error=%s", self.worker_id, type(error).__name__
                    )
                    await self.pause(backoff)
                    backoff = min(30, backoff * 2)
        finally:
            if self.active_task is not None and not self.active_task.done():
                self.active_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self.active_task
            self.health.stop()
