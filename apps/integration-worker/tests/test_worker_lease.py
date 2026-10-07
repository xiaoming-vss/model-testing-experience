import time

from testing_agent_integration_worker.core.errors import ControlPlaneError
from testing_agent_integration_worker.domain.execution import Execution, ExecutionWindow
from testing_agent_integration_worker.schemas.job import ClaimJob
from testing_agent_integration_worker.worker.lease import maintain_lease


def test_late_renewal_cannot_resurrect_an_expired_lease():
    clock = [5.0]
    window = ExecutionWindow(10, margin=1, clock=lambda: clock[0])
    assert window.active()
    clock[0] = 11
    assert not window.renew(11, 60)
    assert not window.active() and window.lost


def test_shutdown_stops_writes_but_allows_the_inflight_request_to_drain():
    window = ExecutionWindow(100, clock=lambda: 10)
    window.stopped = True
    assert not window.active() and window.alive()
    assert window.renew(10, 60)
    assert not window.active() and window.alive()


async def test_heartbeat_failure_immediately_stops_new_writes():
    class Repository:
        async def heartbeat(self, *_):
            raise ControlPlaneError(409)

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
    execution = Execution(claim, ExecutionWindow(time.monotonic() + 60))
    await maintain_lease(Repository(), execution, 0.001, lambda: None)
    assert execution.window.lost and not execution.window.active()
