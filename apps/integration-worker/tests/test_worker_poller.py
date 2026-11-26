import asyncio
import logging
from types import SimpleNamespace

from testing_agent_integration_worker.core.errors import LeaseLost
from testing_agent_integration_worker.schemas.job import ClaimJob
from testing_agent_integration_worker.worker.poller import Poller

LOGGER = "testing_agent_integration_worker.worker.poller"


class ControlPlane:
    """Return one job, then end the poll loop the way a shutdown does."""

    def __init__(self, job):
        self.job = job
        self.claims = 0
        self.poller = None

    async def claim(self, worker_id, request_id):
        self.claims += 1
        if self.claims > 1:
            self.poller.stop_event.set()
            return SimpleNamespace(job=None)
        return SimpleNamespace(job=self.job)

    async def heartbeat(self, *_):
        return 60


async def _replay_evidence():
    return None


def _noop():
    return None


def build_poller(handler):
    claim = ClaimJob(
        jobId="job",
        jobStatus="claimed",
        taskType="zentao_bug_sync",
        protocolVersion=1,
        workerId="worker",
        claimGeneration=1,
        runtimeGeneration="epoch",
        leaseSeconds=60,
    )
    control_plane = ControlPlane(claim)
    settings = SimpleNamespace(
        lease_margin_seconds=0,
        heartbeat_interval_seconds=10,
        poll_interval_seconds=0.01,
        shutdown_grace_seconds=0.01,
    )
    poller = Poller(
        control_plane,
        SimpleNamespace(handle=handler),
        SimpleNamespace(replay_evidence=_replay_evidence),
        settings,
        SimpleNamespace(progress=_noop, stop=_noop),
    )
    control_plane.poller = poller
    return poller


def job_records(caplog):
    return [
        record
        for record in caplog.records
        if record.name == LOGGER and "Job stopped" in record.message
    ]


async def test_lease_lost_is_a_warning_without_traceback(caplog):
    async def lose_lease(execution):
        raise LeaseLost()

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await build_poller(lose_lease).run()

    (record,) = job_records(caplog)
    assert record.levelno == logging.WARNING
    assert record.exc_info is None
    assert record.message.endswith("error=LeaseLost")


async def test_exhausted_shutdown_grace_is_a_warning_without_traceback(caplog):
    started = asyncio.Event()

    async def block(execution):
        started.set()
        await asyncio.Event().wait()

    poller = build_poller(block)
    run = asyncio.create_task(poller.run())
    await started.wait()
    poller.stop_event.set()
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await run
    await cancel_remaining_tasks()

    (record,) = job_records(caplog)
    assert record.levelno == logging.WARNING
    assert record.exc_info is None
    assert record.message.endswith("error=TimeoutError")


async def test_unknown_job_error_keeps_the_error_level_and_traceback(caplog):
    async def crash(execution):
        raise RuntimeError("boom")

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await build_poller(crash).run()

    (record,) = job_records(caplog)
    assert record.levelno == logging.ERROR
    assert record.exc_info is not None
    assert record.message.endswith("error=RuntimeError")


async def cancel_remaining_tasks():
    pending = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
