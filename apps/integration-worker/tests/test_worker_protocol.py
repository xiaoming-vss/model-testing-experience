import json

import httpx
import pytest
from pydantic import ValidationError

from testing_agent_integration_worker.core.config import ControlPlaneSettings
from testing_agent_integration_worker.core.errors import ControlPlaneError
from testing_agent_integration_worker.repositories.control_plane import ControlPlaneRepository
from testing_agent_integration_worker.repositories.evidence import Evidence, EvidenceRepository
from testing_agent_integration_worker.schemas.step import RemoteResult, ResultEvent


async def test_response_loss_reuses_the_exact_claim_request():
    requests = []

    async def handle(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            raise httpx.ReadTimeout("private-upstream-error", request=request)
        return httpx.Response(200, json={"job": None})

    repository = ControlPlaneRepository(
        ControlPlaneSettings(base_url="http://cp.test", worker_token="key"),
        transport=httpx.MockTransport(handle),
    )
    try:
        assert (await repository.claim("worker", "same-request")).job is None
        assert requests[0] == requests[1]
    finally:
        await repository.close()


async def test_http_rejection_does_not_echo_private_body_or_retry():
    count = []

    async def handle(request):
        count.append(1)
        return httpx.Response(403, text="private-body-and-token")

    repository = ControlPlaneRepository(
        ControlPlaneSettings(base_url="http://cp.test", worker_token="key"),
        transport=httpx.MockTransport(handle),
    )
    with pytest.raises(ControlPlaneError) as error:
        await repository.claim("worker", "request")
    await repository.close()
    assert len(count) == 1 and "private-body" not in str(error.value)


def test_result_outbox_survives_restart_and_rejects_access_material(tmp_path):
    path = tmp_path / "evidence.json"
    repository = EvidenceRepository(path)
    event = ResultEvent(
        workerId="worker",
        claimGeneration=1,
        runtimeGeneration="epoch",
        eventId="event",
        operationId="operation",
        status="succeeded",
        result=RemoteResult(remoteBugId=50),
    )
    repository.record(Evidence(jobId="job", stepKey="create_bug", event=event))
    restored = EvidenceRepository(path)
    assert restored.items["event"].event == event
    assert path.stat().st_mode & 0o777 == 0o600
    restored.acknowledge("event")
    assert EvidenceRepository(path).items == {}
    with pytest.raises(ValidationError):
        Evidence.model_validate(
            {
                "jobId": "job",
                "stepKey": "create_bug",
                "event": event.model_dump(by_alias=True),
                "token": "private",
            }
        )
