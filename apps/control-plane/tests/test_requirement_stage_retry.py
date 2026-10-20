import pytest
from support.execution_writer import MemoryExecutionWriter
from support.function_candidate_review import review_client
from support.function_stage_retry import failed_repository

from testing_agent.core.errors import ErrBadRequest, ErrForbidden
from testing_agent.services.ai_generate_task import AiGenerateTaskService


def repository(stage="extracting_text"):
    repo = failed_repository(stage)
    original = repo.get_task

    async def get_task(task_id):
        task = await original(task_id)
        task.task_type = "requirement_analysis"
        return task

    repo.get_task = get_task
    return repo


@pytest.mark.parametrize("stage", ["extracting_text", "feature_understanding"])
def test_retry_http_preserves_stage_connection_and_artifacts(stage):
    repo = repository(stage)
    repo.run.checkpoint_enabled = True
    config = dict(repo.run.config_json)
    output = repo.run.result_yaml
    client = review_client(repo)
    response = client.post("/v1/requirement-analysis-runs/run-1/stage-retry", json={"stage": stage})
    assert response.status_code == 200
    assert response.json()["data"]["currentStage"] == stage
    assert repo.run.status == "pending"
    assert repo.run.config_json == config
    assert repo.run.result_yaml == output
    assert client.app.state.execution_writer.writes[-1][1].operation == "retry"
    assert len(repo.queued) == 1
    assert repo.queued[0].task_type == "requirement_analysis"
    assert client.app.state.execution_writer.writes[-1][1].llm_connection_id == "llm-1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"status": "running"},
        {"status": "pending"},
        {"status": "success"},
        {"status": "waiting_review"},
        {"review_status": "approved"},
        {"review_status": "rejected"},
        {"import_status": "imported"},
        {"current_stage": "completed"},
    ],
)
async def test_retry_rejects_ineligible_runs(changes):
    repo = repository()
    for key, value in changes.items():
        setattr(repo.run, key, value)
    with pytest.raises(type(ErrBadRequest)):
        await AiGenerateTaskService(repo, execution_writer=MemoryExecutionWriter()).retry_stage(
            "run-1", {"stage": "extracting_text"}, "user-1", kind="requirement_analysis"
        )
    assert not repo.queued


@pytest.mark.asyncio
async def test_retry_checks_owner_cross_stage_and_claimed_worker():
    for body, user, worker, error in [
        ({}, "other", "error", ErrForbidden),
        ({"stage": "writing_requirement"}, "user-1", "error", ErrBadRequest),
        ({}, "user-1", "claimed", ErrBadRequest),
    ]:
        repo = repository()
        repo.latest.status = worker
        with pytest.raises(type(error)):
            await AiGenerateTaskService(repo, execution_writer=MemoryExecutionWriter()).retry_stage(
                "run-1", body, user, kind="requirement_analysis"
            )
        assert not repo.queued


@pytest.mark.asyncio
async def test_duplicate_retry_queues_only_once():
    import asyncio

    repo = repository()
    service = AiGenerateTaskService(repo, execution_writer=MemoryExecutionWriter())
    results = await asyncio.gather(
        service.retry_stage("run-1", {}, "user-1", kind="requirement_analysis"),
        service.retry_stage("run-1", {}, "user-1", kind="requirement_analysis"),
        return_exceptions=True,
    )
    assert sum(isinstance(result, dict) for result in results) == 1
    assert len(repo.queued) == 1


@pytest.mark.parametrize(
    "method,suffix,body",
    [
        ("PATCH", "stage-output", {"stage": "feature_understanding", "resultYaml": "changed"}),
        ("POST", "stage-review", {"stage": "feature_understanding", "action": "approve"}),
        ("POST", "stage-review", {"stage": "feature_understanding", "action": "reject"}),
        (
            "POST",
            "stage-revise",
            {"stage": "feature_understanding", "revisionInstruction": "change"},
        ),
        ("POST", "stage-retry", {"stage": "feature_understanding"}),
        ("POST", "import-to-requirement", {}),
    ],
)
def test_rejected_requirement_http_mutations_are_blocked(method, suffix, body):
    from copy import deepcopy

    repo = repository("completed")
    repo.run.status = "success"
    repo.run.stage_status = "completed"
    repo.run.review_status = "rejected"
    before = {
        key: deepcopy(getattr(repo.run, key))
        for key in ["status", "review_status", "config_json", "result_yaml"]
    }
    response = review_client(repo).request(
        method, f"/v1/requirement-analysis-runs/run-1/{suffix}", json=body
    )
    assert response.status_code == 400
    assert {key: getattr(repo.run, key) for key in before} == before
    assert repo.commits == 0
    assert not repo.queued
