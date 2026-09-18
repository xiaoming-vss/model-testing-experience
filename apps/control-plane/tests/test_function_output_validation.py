from types import SimpleNamespace

import pytest
from test_worker_contract import FakeWorkerRepository

from testing_agent.schemas.workers import WorkerProgressRequest, WorkerTaskEventRequest
from testing_agent.services import worker_task as module
from testing_agent.services.worker import apply_ai_completion_to_run
from testing_agent.services.worker_task import WorkerTaskService


def run_record():
    return SimpleNamespace(
        run_id="run",
        checkpoint_enabled=True,
        current_stage="detailed_cases",
        stage_status="running",
        status="running",
        config_json={"requirementAnalysis": {"old": True}, "revisionInstruction": "preserve"},
        result_yaml='{"cases":[{"name":"old"}]}',
        result_summary_json={},
        error_message="",
        snapshot_json={},
        duration_ms=0,
    )


@pytest.mark.parametrize("status", ["error", "failed", "canceled"])
def test_failed_functional_completion_preserves_valid_artifacts(status):
    run = run_record()
    old = run.config_json.copy(), run.result_yaml
    apply_ai_completion_to_run(
        run,
        WorkerTaskEventRequest(
            workerId="w", status=status, configJson={}, resultYaml="", errorMessage="输出校验失败"
        ),
        functional=True,
    )
    assert (run.config_json, run.result_yaml) == old
    assert run.stage_status == "failed"
    assert run.error_message == "输出校验失败"


def test_successful_functional_completion_replaces_artifacts_and_instruction():
    run = run_record()
    apply_ai_completion_to_run(
        run,
        WorkerTaskEventRequest(
            workerId="w",
            status="success",
            configJson={"requirementAnalysis": {"new": True}},
            resultYaml='{"cases":[]}',
        ),
        functional=True,
    )
    assert "revisionInstruction" not in run.config_json
    assert run.result_yaml == '{"cases":[]}'
    assert run.current_stage == "completed"


@pytest.mark.asyncio
async def test_repair_progress_preserves_outputs_and_passes_summary(monkeypatch):
    from unittest.mock import AsyncMock

    from testing_agent.services import worker_task

    monkeypatch.setattr(worker_task, "authorize_execution", AsyncMock())
    run = run_record()
    task = SimpleNamespace(
        task_id="worker-task",
        task_type="functional_case_generate",
        worker_id="w",
        run_id="run",
        status="running",
    )

    class Repository(FakeWorkerRepository):
        async def get_ai_run(self, run_id):
            return run

    async def find_task(*args):
        return task

    monkeypatch.setattr(module, "find_task", find_task)
    event = {
        "outputValidation": {
            "stage": "detailed_cases",
            "module": "登录",
            "repairAttempt": 1,
            "maxRepairs": 2,
            "status": "repairing",
        }
    }
    old = run.config_json.copy(), run.result_yaml
    await WorkerTaskService(Repository(task)).progress(
        "worker-task",
        WorkerProgressRequest(
            workerId="w",
            runId="run",
            currentStage="detailed_cases",
            stageStatus="running",
            configJson="",
            resultYaml="",
            resultSummaryJson=event,
        ),
    )
    assert (run.config_json, run.result_yaml) == old
    assert run.result_summary_json == event
    assert run.status == "running"
