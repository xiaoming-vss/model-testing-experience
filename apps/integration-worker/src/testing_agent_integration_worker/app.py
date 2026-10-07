import asyncio
import signal

from testing_agent_integration_worker.gateways.zentao import ZentaoGateway
from testing_agent_integration_worker.handlers.jobs import JobHandler
from testing_agent_integration_worker.repositories.control_plane import ControlPlaneRepository
from testing_agent_integration_worker.repositories.evidence import EvidenceRepository
from testing_agent_integration_worker.services.bug_sync import BugWorkflow
from testing_agent_integration_worker.services.step_execution import StepExecution
from testing_agent_integration_worker.worker.lifecycle import Health
from testing_agent_integration_worker.worker.poller import Poller


def create_worker(settings, *, control_plane=None, gateway_factory=ZentaoGateway) -> Poller:
    repository = control_plane or ControlPlaneRepository(settings.control_plane)
    health = Health(settings.worker.health_file)
    evidence = EvidenceRepository(settings.worker.evidence_file)
    steps = StepExecution(repository, gateway_factory, evidence, progress=health.progress)
    workflow = BugWorkflow(repository, gateway_factory, steps)
    return Poller(repository, JobHandler(workflow), steps, settings.worker, health)


async def run_worker(settings) -> None:
    worker = create_worker(settings)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, worker.stop)
    try:
        await worker.run()
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)
        await worker.control_plane.close()
