from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db

from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.services.stage_storage import DirectStageStorage
from testing_agent.services.stage_storage.worker import StageWorkerTransitions


async def test_progress_is_accepted_without_persisting_details_and_failure_is_visible(db):  # noqa: F811
    seed_task(db)
    stage = AiGenerationStage(id="stage-progress", task_id="task", stage="case_names")
    db.add(stage)
    db.commit()
    session = AsyncSessionAdapter(db)
    attempt = await DirectStageStorage(session).prepare(
        stage.id, worker_task_id="worker-progress", requested_by="u", input_snapshot={}
    )
    worker = StageWorkerTransitions(session)
    await worker.started(stage.id, attempt.id, "worker-progress")
    await worker.progress(stage.id, attempt.id, "worker-progress", {"summary": "detail"})
    await worker.failed(stage.id, attempt.id, "worker-progress", error_message="failure")
    assert attempt.error_message == "failure"
    assert attempt.status == "failed"
    assert "progress_json" not in AiGenerationAttempt.__table__.columns
    assert "remediation" not in AiGenerationAttempt.__table__.columns
