from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, create_run
from support.ai_execution import db as db

from testing_agent.domain.ai_execution_intent import ExecutionIntent
from testing_agent.models.ai_generate_execution import AiGenerateRunStage
from testing_agent.models.ai_generate_task import AiGenerateTaskRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.ai_execution import persist_run


def final_artifact(session, run_id):
    return session.scalar(
        select(AiGenerateRunStage.current_artifact_attempt_id).where(
            AiGenerateRunStage.run_id == run_id, AiGenerateRunStage.stage == "detailed_cases"
        )
    )


async def test_plain_repository_commit_does_not_publish_execution_output(db):
    run, worker = create_run(db, checkpoint=False)
    run.status = "success"
    run.current_stage = "completed"
    run.result_yaml = '{"cases":[]}'
    repository = AiGenerateTaskRepository(AsyncSessionAdapter(db))
    await repository.commit()
    assert final_artifact(db, run.run_id) is None

    persist_run(db, run, intent=ExecutionIntent(worker_event_id=worker.task_id), worker=worker)
    db.commit()
    assert final_artifact(db, run.run_id) is not None


def test_explicit_save_does_not_publish_other_observed_runs(db):
    first, first_worker = create_run(db, checkpoint=False)
    other = AiGenerateTaskRun(
        run_id="other",
        task_id=first.task_id,
        trigger_user_id="u",
        status="pending",
        checkpoint_enabled=False,
        current_stage="",
        config_json={},
        snapshot_json={},
    )
    other_worker = WorkerTask(
        domain="ai", task_id="other-worker", task_type="functional_case_generate", run_id="other"
    )
    db.add_all([other, other_worker])
    persist_run(db, other, worker=other_worker)
    db.commit()
    for run in (first, other):
        run.status = "success"
        run.current_stage = "completed"
        run.result_yaml = '{"cases":[]}'
    persist_run(db, first, worker=first_worker)
    db.commit()
    assert final_artifact(db, first.run_id) is not None
    assert final_artifact(db, other.run_id) is None
