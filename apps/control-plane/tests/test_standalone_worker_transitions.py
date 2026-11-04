"""Independent Worker events cannot mutate another execution's attempts."""

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.standalone_execution import start_standalone_execution
from testing_agent.services.standalone_worker_transitions import StandaloneWorkerTransitions


async def test_continuous_worker_advances_its_own_attempts_and_rejects_late_events(db):  # noqa: F811
    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    first, initial, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="run-one",
        request_id="worker-one",
        actor_id="actor",
        connection_id="llm",
        source={"sourceContent": "one"},
        config={},
        checkpoint_enabled=False,
    )
    second, other, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="run-two",
        request_id="worker-two",
        actor_id="other",
        connection_id="llm",
        source={"sourceContent": "two"},
        config={},
        checkpoint_enabled=False,
    )
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "worker-one"))
    transitions = StandaloneWorkerTransitions(session)
    await transitions.claimed(task, queue)
    await transitions.started(task, queue)
    assert first.workflow_status == initial.status == "running"
    next_attempt = await transitions.advance(
        task,
        queue,
        next_stage="case_names",
        content='{"analysis":1}',
        output_format="json",
        next_config={"requirementAnalysis": {"analysis": 1}},
    )
    assert initial.status == "success" and first.current_stage == "case_names"
    assert (
        next_attempt.execution_id == first.execution_id
        and next_attempt.worker_task_id == "worker-one"
    )
    assert queue.run_id == initial.id and second.workflow_status == other.status == "pending"
    final_attempt = await transitions.advance(
        task,
        queue,
        next_stage="detailed_cases",
        content='{"cases":1}',
        output_format="json",
        next_config={"requirementAnalysis": {"analysis": 1}, "caseNames": {"cases": 1}},
    )
    assert final_attempt.review_status == "pending"
    await transitions.completed(task, queue, content="final", output_format="yaml")
    assert first.workflow_status == "success" and first.current_stage == "completed"
    assert final_attempt.output_content == "final" and first.finished_at is not None
    with pytest.raises(AppError):
        await transitions.failed(task, queue, status="failed", error_message="late")
    assert final_attempt.output_content == "final" and second.workflow_status == "pending"


async def test_checkpoint_and_failed_dispatch_are_isolated(db):  # noqa: F811
    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    execution, attempt, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="checkpoint",
        request_id="checkpoint-worker",
        actor_id="u",
        connection_id="llm",
        source={},
        config={},
        checkpoint_enabled=True,
    )
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "checkpoint-worker"))
    transitions = StandaloneWorkerTransitions(session)
    await transitions.claimed(task, queue)
    await transitions.started(task, queue)
    with pytest.raises(AppError):
        await transitions.advance(
            task, queue, next_stage="case_names", content="{}", output_format="json", next_config={}
        )
    await transitions.completed(task, queue, content="{}", output_format="json")
    assert execution.workflow_status == "waiting_review"
    assert attempt.review_status == "pending" and execution.finished_at is None
    with pytest.raises(AppError):
        await transitions.failed(task, queue, status="failed", error_message="late")


async def test_failed_attempt_does_not_replace_other_execution_success(db):  # noqa: F811
    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    completed, result, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="prior",
        request_id="prior-worker",
        actor_id="u",
        connection_id="llm",
        source={},
        config={},
        checkpoint_enabled=True,
    )
    failed, failed_attempt, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="failed",
        request_id="failed-worker",
        actor_id="u",
        connection_id="llm",
        source={},
        config={},
        checkpoint_enabled=True,
    )
    completed.workflow_status = "success"
    result.status, result.output_content = "success", '{"old":true}'
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "failed-worker"))
    transitions = StandaloneWorkerTransitions(session)
    await transitions.claimed(task, queue)
    await transitions.started(task, queue)
    await transitions.failed(task, queue, status="failed", error_message="worker failure")
    assert failed.workflow_status == failed_attempt.status == "failed"
    assert failed_attempt.error_message == "worker failure" and failed.finished_at is not None
    assert completed.workflow_status == "success" and result.output_content == '{"old":true}'
    with pytest.raises(AppError):
        await transitions.completed(task, queue, content="late", output_format="text")
