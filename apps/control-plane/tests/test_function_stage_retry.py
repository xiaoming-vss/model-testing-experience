import asyncio

import pytest
from test_function_candidate_review import review_client
from test_function_stage_revise import RevisionRepository, revision_run

from testing_agent.core.errors import ErrBadRequest, ErrForbidden
from testing_agent.services.ai_generate_task import AiGenerateTaskService


def failed_repository(stage="requirement_analysis", stage_status="failed"):
    run = revision_run(stage)
    run.status = "error"
    run.stage_status = stage_status
    run.error_message = "Unterminated string"
    run.config_json["revisionInstruction"] = "keep this round's instruction"
    repo = RevisionRepository(run)
    repo.latest.status = "error"
    return repo


@pytest.mark.parametrize("checkpoint", [False, True])
@pytest.mark.parametrize("stage", ["requirement_analysis", "case_names", "detailed_cases"])
@pytest.mark.parametrize("stage_status", ["failed", "retrying"])
def test_retry_http_requeues_failed_stage_and_preserves_inputs(stage, stage_status, checkpoint):
    repo = failed_repository(stage, stage_status)
    repo.run.checkpoint_enabled = checkpoint
    config = dict(repo.run.config_json)
    response = review_client(repo).post(
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
    assert repo.queued[0].llm_connection_id == "llm-1"
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
        await AiGenerateTaskService(repo).retry_stage(
            "run-1", {"stage": "requirement_analysis"}, "user-1"
        )
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
            await AiGenerateTaskService(repo).retry_stage("run-1", body, "user-1")
        assert not repo.queued


@pytest.mark.asyncio
async def test_retry_checks_ownership_and_concurrent_requests_queue_once():
    repo = failed_repository()
    service = AiGenerateTaskService(repo)
    with pytest.raises(type(ErrForbidden)):
        await service.retry_stage("run-1", {}, "other-user")
    results = await asyncio.gather(
        service.retry_stage("run-1", {}, "user-1"),
        service.retry_stage("run-1", {}, "user-1"),
        return_exceptions=True,
    )
    assert sum(isinstance(result, dict) for result in results) == 1
    assert len(repo.queued) == 1
