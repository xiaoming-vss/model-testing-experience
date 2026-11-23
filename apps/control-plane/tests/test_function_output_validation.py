from types import SimpleNamespace

import pytest
from support.worker_contract import FakeWorkerRepository

from testing_agent.core.errors import AppError
from testing_agent.schemas.workers import WorkerProgressRequest
from testing_agent.services import worker_task as module
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


@pytest.mark.asyncio
async def test_legacy_repair_progress_cannot_change_output(monkeypatch):
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
    old = run.config_json.copy(), run.result_yaml
    with pytest.raises(AppError) as rejected:
        await WorkerTaskService(Repository(task)).progress(
            "worker-task",
            WorkerProgressRequest(
                workerId="w",
                runId="run",
                currentStage="detailed_cases",
                stageStatus="running",
                configJson="",
                resultYaml="",
                resultSummaryJson={"outputValidation": {"status": "repairing"}},
            ),
        )
    assert rejected.value.http_code == 404
    assert (run.config_json, run.result_yaml) == old
