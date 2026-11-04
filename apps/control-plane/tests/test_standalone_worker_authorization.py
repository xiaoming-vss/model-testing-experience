"""Worker authority remains tied to its own dispatch and execution."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services import standalone_worker_authorization as auth
from testing_agent.services.standalone_execution import start_standalone_execution


async def test_authority_follows_current_attempt_only_within_own_dispatch(db, monkeypatch):  # noqa: F811
    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    execution, initial, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="run",
        request_id="worker",
        actor_id="user",
        connection_id="llm",
        source={},
        config={},
        checkpoint_enabled=False,
    )
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "worker"))
    actor = AsyncMock(return_value="user")
    monkeypatch.setattr(auth, "authorize_worker_actor", actor)
    authority = await auth.authorize_standalone_worker(session, queue, pending=True)
    assert authority.dispatched_attempt.id == authority.current_attempt.id == initial.id
    assert authority.execution.execution_id == "run"
    actor.assert_awaited_once_with(session, task, initial)
    with pytest.raises(AppError):
        await auth.authorize_standalone_worker(session, queue)

    initial.status = "success"
    execution.workflow_status = "running"
    execution.current_stage = "case_names"
    queue.status = "running"
    stage = AiGenerationStage(id="next-stage", task_id=task.task_id, stage="case_names")
    db.add(stage)
    db.flush()
    current = AiGenerationAttempt(
        id="next-attempt",
        stage_id=stage.id,
        execution_id="run",
        attempt_no=1,
        operation="generate",
        worker_task_id="worker",
        requested_by="user",
        input_snapshot_json={"llmConnectionId": "llm"},
        status="running",
        invalidated_reason="",
    )
    db.add(current)
    db.flush()
    authority = await auth.authorize_standalone_worker(session, queue)
    assert authority.dispatched_attempt.id == initial.id
    assert authority.current_attempt.id == current.id
    assert authority.current_stage.stage == "case_names"

    current.input_snapshot_json = {"llmConnectionId": "other"}
    db.flush()
    with pytest.raises(AppError):
        await auth.authorize_standalone_worker(session, queue)
    current.input_snapshot_json = {"llmConnectionId": "llm"}
    current.requested_by = "other"
    db.flush()
    with pytest.raises(AppError):
        await auth.authorize_standalone_worker(session, queue)
    current.requested_by = "user"
    current.worker_task_id = "other-worker"
    db.flush()
    with pytest.raises(AppError):
        await auth.authorize_standalone_worker(session, queue)
    current.worker_task_id = "worker"
    execution.workflow_status = "failed"
    db.flush()
    with pytest.raises(AppError):
        await auth.authorize_standalone_worker(session, queue)


async def test_worker_payload_keeps_dispatched_attempt_id_and_checkpoint_mode(db, monkeypatch):  # noqa: F811
    import json

    from testing_agent.services.standalone_worker_payload import standalone_worker_payloads

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    execution, attempt, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="public-run",
        request_id="worker-task",
        actor_id="user",
        connection_id="llm",
        source={"sourceContent": "frozen"},
        config={"setting": "frozen"},
        checkpoint_enabled=False,
    )
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "worker-task"))
    monkeypatch.setattr(auth, "authorize_worker_actor", AsyncMock(return_value="user"))
    authority = await auth.authorize_standalone_worker(session, queue, pending=True)
    claim, snapshot = standalone_worker_payloads(authority, queue, lease_seconds=30)
    assert execution.execution_id == "public-run"
    assert claim["attemptId"] == snapshot["run"]["attemptId"] == attempt.id
    assert claim["taskId"] == "worker-task" and claim["llmConnectionId"] == "llm"
    assert claim["checkpointEnabled"] is snapshot["checkpointEnabled"] is False
    assert snapshot["run"]["sourceContent"] == "frozen"
    assert json.loads(snapshot["configJson"]) == {"setting": "frozen"}


async def test_revision_payload_contains_the_frozen_current_candidate(db, monkeypatch):  # noqa: F811
    import json

    from testing_agent.services.standalone_worker_payload import standalone_worker_payloads

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    _, attempt, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="run",
        request_id="worker",
        actor_id="user",
        connection_id="llm",
        source={},
        config={"setting": "fixed"},
        checkpoint_enabled=True,
    )
    attempt.revision_instruction = "correct it"
    attempt.input_snapshot_json = {
        **attempt.input_snapshot_json,
        "currentOutput": '{"purpose":"login"}',
    }
    db.flush()
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "worker"))
    monkeypatch.setattr(auth, "authorize_worker_actor", AsyncMock(return_value="user"))
    authority = await auth.authorize_standalone_worker(session, queue, pending=True)
    claim, _ = standalone_worker_payloads(authority, queue, lease_seconds=30)
    config = json.loads(claim["configJson"])
    assert config["requirementAnalysis"] == {"purpose": "login"}
    assert config["revisionInstruction"] == "correct it"
    assert "requirementAnalysis" not in attempt.input_snapshot_json["config"]
