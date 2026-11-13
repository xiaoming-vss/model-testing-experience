"""Module progress survives polling and cannot overwrite another attempt or artifact."""

import copy

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task
from support.ai_execution import db as db

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.services.stage_storage import DirectStageStorage
from testing_agent.services.stage_storage.views import build_stage_views
from testing_agent.services.stage_storage.worker import StageWorkerTransitions


def snapshot(sequence=1):
    return {
        "moduleGeneration": {
            "sequence": sequence,
            "concurrency": 2,
            "status": "running",
            "modules": [
                {
                    "id": "0",
                    "module": "文件校验",
                    "status": "running",
                    "elapsedMs": 0,
                    "caseCount": 0,
                    "repairAttempt": 0,
                }
            ],
        }
    }


async def setup(session):
    seed_task(session)
    stage = AiGenerationStage(
        id="modules", task_id="task", stage="detailed_cases", next_version_no=1
    )
    session.add(stage)
    session.commit()
    storage = DirectStageStorage(AsyncSessionAdapter(session))
    attempt = await storage.prepare(
        stage.id, worker_task_id="modules-worker", requested_by="u", input_snapshot={}
    )
    worker = StageWorkerTransitions(AsyncSessionAdapter(session))
    await worker.started(stage.id, attempt.id, "modules-worker")
    return stage, attempt, storage, worker


async def test_progress_visible_after_poll_and_older_snapshots_are_ignored(db):
    stage, attempt, _, worker = await setup(db)
    await worker.progress(stage.id, attempt.id, "modules-worker", {"summary": snapshot(2)})
    await worker.progress(stage.id, attempt.id, "modules-worker", {"summary": snapshot(1)})
    await worker.progress(
        stage.id,
        attempt.id,
        "modules-worker",
        {"summary": {"outputValidation": {"status": "generating"}}},
    )
    db.commit()
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    view = await build_stage_views(AsyncSessionAdapter(db), task, "function", detail=True)
    progress = next(s for s in view.stages if s.stage == "detailed_cases").module_generation
    assert progress.attempt_id == attempt.id
    assert progress.sequence == 2
    assert progress.modules[0].module == "文件校验"
    assert attempt.output_content is None
    assert set(attempt.output_context_json) == {"moduleGeneration"}


@pytest.mark.parametrize(
    "mutation",
    ["unknown_field", "invalid_status", "duplicate_id", "false_completion", "changed_identity"],
)
async def test_progress_rejects_invalid_or_arbitrary_payload(db, mutation):
    stage, attempt, _, worker = await setup(db)
    await worker.progress(stage.id, attempt.id, "modules-worker", {"summary": snapshot()})
    value = snapshot(2)
    progress = value["moduleGeneration"]
    if mutation == "unknown_field":
        progress["prompt"] = "must not be stored"
    elif mutation == "invalid_status":
        progress["modules"][0]["status"] = "invented"
    elif mutation == "duplicate_id":
        progress["modules"].append(copy.deepcopy(progress["modules"][0]))
    elif mutation == "false_completion":
        progress["status"] = "completed"
    else:
        progress["modules"][0]["module"] = "another module"
    with pytest.raises(AppError):
        await worker.progress(stage.id, attempt.id, "modules-worker", {"summary": value})
    assert attempt.output_context_json["moduleGeneration"]["sequence"] == 1


async def test_failure_stops_progress_and_next_attempt_does_not_reuse_it(db):
    stage, attempt, storage, worker = await setup(db)
    await worker.progress(stage.id, attempt.id, "modules-worker", {"summary": snapshot()})
    await worker.failed(stage.id, attempt.id, "modules-worker", error_message="failed")
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    view = await build_stage_views(AsyncSessionAdapter(db), task, "function", detail=True)
    progress = next(s for s in view.stages if s.stage == "detailed_cases").module_generation
    assert progress.status == "failed"
    assert progress.modules[0].status == "canceled"
    next_attempt = await storage.prepare(
        stage.id, worker_task_id="next-worker", requested_by="u", input_snapshot={}
    )
    view = await build_stage_views(AsyncSessionAdapter(db), task, "function", detail=True)
    assert next(s for s in view.stages if s.stage == "detailed_cases").module_generation is None
    with pytest.raises(AppError):
        await worker.progress(stage.id, attempt.id, "modules-worker", {"summary": snapshot(2)})
    assert next_attempt.output_context_json is None


async def test_completion_keeps_progress_with_output_metadata(db):
    stage, attempt, _, worker = await setup(db)
    value = snapshot()
    value["moduleGeneration"]["status"] = "completed"
    value["moduleGeneration"]["modules"][0]["status"] = "completed"
    await worker.progress(stage.id, attempt.id, "modules-worker", {"summary": value})
    await worker.completed(
        stage.id,
        attempt.id,
        "modules-worker",
        content='{"cases":[]}',
        output_format="json",
        output_context={"caseCount": 0},
    )
    assert attempt.output_context_json["moduleGeneration"]["status"] == "completed"
    assert attempt.output_context_json["caseCount"] == 0


async def test_worker_string_summary_reaches_stage_projection(db):
    import json

    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.schemas.workers import WorkerProgressRequest
    from testing_agent.services.stage_storage.worker_events import apply_stage_progress

    stage, attempt, _, _ = await setup(db)
    queue = WorkerTask(
        domain="ai",
        task_type="functional_case_generate",
        task_id="modules-worker",
        run_id=attempt.id,
        worker_id="node",
        status="running",
    )
    body = WorkerProgressRequest.model_validate(
        {
            "workerId": "node",
            "taskId": queue.task_id,
            "attemptId": attempt.id,
            "currentStage": "detailed_cases",
            "stageStatus": "running",
            "configJson": "",
            "resultSummaryJson": json.dumps(snapshot()),
        }
    )
    await apply_stage_progress(
        AsyncSessionAdapter(db),
        queue,
        stage_id=stage.id,
        attempt_id=attempt.id,
        kind="function",
        stage="detailed_cases",
        source={},
        frozen_config={},
        body=body,
    )
    assert attempt.output_context_json["moduleGeneration"]["sequence"] == 1


async def test_manual_edit_does_not_claim_another_attempts_module_progress(db):
    stage, attempt, storage, worker = await setup(db)
    await worker.progress(stage.id, attempt.id, "modules-worker", {"summary": snapshot()})
    await worker.completed(
        stage.id,
        attempt.id,
        "modules-worker",
        content='{"cases":[]}',
        output_format="json",
        output_context={"source": "keep"},
    )
    edited = await storage.save_draft(
        stage.id,
        expected_attempt_id=attempt.id,
        requested_by="u",
        content='{"cases":[]}',
        output_format="json",
    )
    assert edited.output_context_json == {"source": "keep"}
    assert "moduleGeneration" in attempt.output_context_json


async def test_point_review_progress_is_persisted_and_projected_on_its_stage(db):
    stage, attempt, _, worker = await setup(db)
    stage.stage = "case_names"
    value = snapshot()
    value["moduleGeneration"].update(
        stage="case_names", status="reviewing", reviewRound=1, issueCount=0
    )
    value["moduleGeneration"]["modules"][0].update(status="completed", pointCount=7)
    await worker.progress(stage.id, attempt.id, "modules-worker", {"summary": value})
    value["moduleGeneration"].update(sequence=2, status="review_failed", issueCount=3)
    await worker.progress(stage.id, attempt.id, "modules-worker", {"summary": value})
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    view = await build_stage_views(AsyncSessionAdapter(db), task, "function", detail=True)
    progress = next(s for s in view.stages if s.stage == "case_names").module_generation
    assert progress.stage == "case_names"
    assert progress.status == "review_failed"
    assert progress.issue_count == 3
    assert progress.modules[0].point_count == 7
    assert attempt.output_content is None


@pytest.mark.parametrize("state", ["reviewing", "revising", "review_failed"])
async def test_case_generation_cannot_claim_test_point_review_status(db, state):
    stage, attempt, _, worker = await setup(db)
    value = snapshot()
    value["moduleGeneration"]["status"] = state
    value["moduleGeneration"]["modules"][0]["status"] = "completed"
    with pytest.raises(AppError):
        await worker.progress(stage.id, attempt.id, "modules-worker", {"summary": value})
    value["moduleGeneration"]["stage"] = "case_names"
    with pytest.raises(AppError):
        await worker.progress(stage.id, attempt.id, "modules-worker", {"summary": value})
