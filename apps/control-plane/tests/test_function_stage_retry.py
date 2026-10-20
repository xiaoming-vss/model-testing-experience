import asyncio

import pytest
from support.execution_writer import MemoryExecutionWriter
from support.function_candidate_review import review_client
from support.function_stage_retry import (
    failed_repository as failed_repository,
)
from support.generation import generation_services

from testing_agent.core.errors import ErrBadRequest, ErrForbidden


@pytest.mark.parametrize("checkpoint", [False, True])
@pytest.mark.parametrize("stage", ["requirement_analysis", "case_names", "detailed_cases"])
@pytest.mark.parametrize("stage_status", ["failed", "retrying"])
def test_retry_http_requeues_failed_stage_and_preserves_inputs(stage, stage_status, checkpoint):
    repo = failed_repository(stage, stage_status)
    repo.run.checkpoint_enabled = checkpoint
    config = dict(repo.run.config_json)
    client = review_client(repo)
    response = client.post(
        "/v1/function-case-generate-task-runs/run-1/stage-retry", json={"stage": stage}
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "pending"
    assert repo.run.stage_status == "pending"
    assert repo.run.current_stage == stage
    assert repo.run.error_message == ""
    assert repo.run.config_json == config
    assert len(repo.queued) == 1
    assert repo.queued[0].run_id == "run-1"
    assert client.app.state.execution_writer.writes[-1][1].llm_connection_id == "llm-1"
    assert repo.commits == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"status": "running"},
        {"status": "success"},
        {"status": "waiting_review"},
        {"current_stage": "completed"},
        {"review_status": "approved"},
        {"import_status": "imported"},
    ],
)
async def test_retry_rejects_invalid_state(changes):
    repo = failed_repository()
    for key, value in changes.items():
        setattr(repo.run, key, value)
    with pytest.raises(type(ErrBadRequest)):
        await generation_services(
            repo, execution_writer=MemoryExecutionWriter()
        ).stages.retry_stage("run-1", {"stage": "requirement_analysis"}, "user-1")
    assert not repo.queued


@pytest.mark.asyncio
async def test_retry_rejects_cross_stage_and_active_worker():
    for body, worker_status in [
        ({"stage": "case_names"}, "error"),
        ({"stage": "requirement_analysis"}, "running"),
    ]:
        repo = failed_repository()
        repo.latest.status = worker_status
        with pytest.raises(type(ErrBadRequest)):
            await generation_services(
                repo, execution_writer=MemoryExecutionWriter()
            ).stages.retry_stage("run-1", body, "user-1")
        assert not repo.queued


@pytest.mark.asyncio
async def test_retry_checks_ownership_and_concurrent_requests_queue_once():
    repo = failed_repository()
    service = generation_services(repo, execution_writer=MemoryExecutionWriter())
    with pytest.raises(type(ErrForbidden)):
        await service.stages.retry_stage("run-1", {}, "other-user")
    results = await asyncio.gather(
        service.stages.retry_stage("run-1", {}, "user-1"),
        service.stages.retry_stage("run-1", {}, "user-1"),
        return_exceptions=True,
    )
    assert sum(isinstance(result, dict) for result in results) == 1
    assert len(repo.queued) == 1
