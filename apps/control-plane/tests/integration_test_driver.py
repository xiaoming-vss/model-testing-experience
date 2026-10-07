"""Exercise the new public API and real Worker workflow with fixture transports.

The returned response is the actual final GET, never a fabricated synchronous POST.
Admission failures are returned unchanged. External MCP is the test's existing fake.
"""

import asyncio
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import event

from testing_agent.core.config import IntegrationExecutionSettings, get_settings

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "integration-worker/src"))
from testing_agent_integration_worker.core.config import ControlPlaneSettings
from testing_agent_integration_worker.core.errors import ControlPlaneError
from testing_agent_integration_worker.domain.execution import Execution, ExecutionWindow
from testing_agent_integration_worker.gateways.zentao import ZentaoGateway
from testing_agent_integration_worker.repositories.control_plane import ControlPlaneRepository
from testing_agent_integration_worker.repositories.evidence import EvidenceRepository
from testing_agent_integration_worker.services.bug_sync import BugWorkflow
from testing_agent_integration_worker.services.step_execution import StepExecution


def enable(api):
    if getattr(api.app.state, "integration_driver_configured", False):
        return api.app.state.settings
    settings = replace(
        api.app.state.settings,
        integration_worker_key="migration-worker-fixture-key",
        integration_execution=IntegrationExecutionSettings(
            enabled=True,
            all_projects=True,
            runtime_generation="migration-fixture",
        ),
    )
    api.app.state.settings = settings
    api.app.dependency_overrides[get_settings] = lambda: settings
    api.app.state.integration_driver_configured = True
    engine = api.app.state.test_sessions.kw["bind"]

    @event.listens_for(engine.sync_engine, "begin")
    def explicit_transaction(connection):
        connection.exec_driver_sql("BEGIN")

    return settings


def dispatch_sync(api, state, *, headers=None, json=None):
    return dispatch(api, state, "zentao-sync-jobs", headers=headers, body=json)


def dispatch_fields(api, state, *, headers=None, json=None):
    return dispatch(api, state, "zentao-field-update-jobs", headers=headers, body=json)


def dispatch(api, state, suffix, *, headers=None, body=None):
    settings = enable(api)
    headers = headers or state["owner"]
    url = state["url"].removesuffix("/zentao-push")
    admitted = api.post(
        url + "/" + suffix, headers=headers, json={**(body or {}), "requestId": uuid4().hex}
    )
    if admitted.status_code != 202:
        return admitted
    job = admitted.json()["data"]["jobId"]

    async def run():
        async def control_plane(request):
            response = await asyncio.to_thread(
                api.request,
                request.method,
                str(request.url),
                headers=dict(request.headers),
                content=request.content,
            )
            return httpx.Response(
                response.status_code, content=response.content, headers=dict(response.headers)
            )

        repository = ControlPlaneRepository(
            ControlPlaneSettings(
                base_url="http://testserver", worker_token=settings.integration_worker_key
            ),
            transport=httpx.MockTransport(control_plane),
        )

        def factory(access):
            return ZentaoGateway(access, transport=httpx.MockTransport(state["remote"].handle))

        try:
            claimed = (await repository.claim("test-worker-" + uuid4().hex, uuid4().hex)).job
            assert claimed is not None and claimed.job_id == job
            with tempfile.TemporaryDirectory(prefix="worker-protocol-fixture-") as directory:
                steps = StepExecution(
                    repository, factory, EvidenceRepository(Path(directory) / "evidence.json")
                )
                workflow = BugWorkflow(repository, factory, steps)
                execution = Execution(
                    claimed, ExecutionWindow(time.monotonic() + claimed.lease_seconds - 2)
                )
                try:
                    await workflow.run(execution)
                except ControlPlaneError as error:
                    # Actual Poller handles permission/lease rejection identically.
                    assert error.status in {403, 404, 409}
        finally:
            await repository.close()

    asyncio.run(run())
    response = api.get(url + "/zentao-jobs/" + job, headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["jobStatus"] not in ("queued", "claimed", "running")
    return api.get(state["url"], headers=headers)
