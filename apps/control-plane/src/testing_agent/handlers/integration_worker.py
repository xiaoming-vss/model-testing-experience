from typing import Annotated

from fastapi import Depends, Query, Response

from testing_agent.api.deps import get_integration_bug_service
from testing_agent.schemas.integration_job import (
    IntegrationClaimRequest,
    IntegrationFailureRequest,
    IntegrationPrepareRequest,
    IntegrationResultRequest,
    IntegrationWorkerIdentity,
)


def no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"


def query_identity(
    worker_id: Annotated[str, Query(alias="workerId", min_length=1, max_length=128)],
    claim_generation: Annotated[int, Query(alias="claimGeneration", gt=0)],
    runtime_generation: Annotated[
        str,
        Query(
            alias="runtimeGeneration", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$"
        ),
    ],
):
    return IntegrationWorkerIdentity(
        worker_id=worker_id,
        claim_generation=claim_generation,
        runtime_generation=runtime_generation,
    )


async def claim(body: IntegrationClaimRequest, service=Depends(get_integration_bug_service)):
    return await service.claim(body)


async def input(
    job_id: str, identity=Depends(query_identity), service=Depends(get_integration_bug_service)
):
    return await service.input(job_id, identity)


async def access(
    job_id: str, body: IntegrationWorkerIdentity, service=Depends(get_integration_bug_service)
):
    return await service.access(job_id, body)


async def heartbeat(
    job_id: str, body: IntegrationWorkerIdentity, service=Depends(get_integration_bug_service)
):
    return await service.heartbeat(job_id, body)


async def prepare(
    job_id: str,
    step_key: str,
    body: IntegrationPrepareRequest,
    service=Depends(get_integration_bug_service),
):
    return await service.prepare(job_id, step_key, body)


async def result(
    job_id: str,
    step_key: str,
    body: IntegrationResultRequest,
    service=Depends(get_integration_bug_service),
):
    return await service.result(job_id, step_key, body)


async def evidence(
    job_id: str,
    step_key: str,
    body: IntegrationResultRequest,
    service=Depends(get_integration_bug_service),
):
    return await service.result(job_id, step_key, body, evidence=True)


async def failure(
    job_id: str,
    step_key: str,
    body: IntegrationFailureRequest,
    service=Depends(get_integration_bug_service),
):
    return await service.failure(job_id, step_key, body)


async def completed(
    job_id: str, body: IntegrationWorkerIdentity, service=Depends(get_integration_bug_service)
):
    return await service.completed(job_id, body)
