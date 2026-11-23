"""Direct-stage transaction and worker/view regression tests."""

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db
from support.direct_stage_storage import (
    setup_stage,
)

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generation_stage import AiGenerationStage


async def test_direct_requirement_worker_refuses_changed_source_document(db, monkeypatch):  # noqa: F811
    from unittest.mock import AsyncMock

    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.requirement import Requirement
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.repositories.worker_task import WorkerTaskRepository
    from testing_agent.services.stage_storage import authorization
    from testing_agent.services.worker_task import WorkerTaskService

    stage, storage = setup_stage(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == stage.task_id))
    task.task_type = "requirement_analysis"
    stage.stage = "extracting_text"
    requirement = db.scalar(select(Requirement).where(Requirement.requirement_id == "r"))
    requirement.document_file_id = "file-1"
    requirement.document_hash = "same"
    attempt = await storage.prepare(
        stage.id,
        worker_task_id="doc-worker",
        requested_by="u",
        input_snapshot={
            "source": {"workflowVersion": 2, "documentFileId": "file-1", "documentHash": "same"},
            "config": {},
            "llmConnectionId": "llm",
        },
    )
    queue = WorkerTask(
        domain="ai",
        task_id="doc-worker",
        task_type="requirement_analysis",
        run_id=attempt.id,
        status="claimed",
    )
    db.add(queue)
    db.commit()
    monkeypatch.setattr(authorization, "require_project_id", AsyncMock())
    monkeypatch.setattr(authorization, "require_personal_connection", AsyncMock())
    service = WorkerTaskService(WorkerTaskRepository(AsyncSessionAdapter(db)))
    assert (await service.requirement_document(queue.task_id)).document_file_id == "file-1"
    requirement.document_hash = "different"
    db.flush()
    with pytest.raises(AppError):
        await service.requirement_document(queue.task_id)


async def test_dispatch_retry_reuses_queue_and_attempt(db):  # noqa: F811
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.services.stage_storage.dispatch import dispatch_stage_attempt

    stage, _ = setup_stage(db)
    adapter = AsyncSessionAdapter(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == stage.task_id))
    original, reused = await dispatch_stage_attempt(
        adapter,
        task=task,
        stage_id=stage.id,
        request_id="request-1",
        actor_id="u",
        input_snapshot={"source": {}, "config": {}, "llmConnectionId": "llm"},
    )
    again, repeated = await dispatch_stage_attempt(
        adapter,
        task=task,
        stage_id=stage.id,
        request_id="request-1",
        actor_id="u",
        input_snapshot={"source": {}, "config": {}, "llmConnectionId": "llm"},
    )
    assert not reused and repeated and again.id == original.id
    queues = db.scalars(select(WorkerTask).where(WorkerTask.task_id == "request-1")).all()
    assert len(queues) == 1 and queues[0].run_id == original.id
    with pytest.raises(AppError):
        await dispatch_stage_attempt(
            adapter,
            task=task,
            stage_id=stage.id,
            request_id="request-1",
            actor_id="other",
            input_snapshot={},
        )
    with pytest.raises(AppError):
        await dispatch_stage_attempt(
            adapter,
            task=task,
            stage_id=stage.id,
            request_id="different-request",
            actor_id="u",
            input_snapshot={},
        )
    assert db.scalar(select(WorkerTask).where(WorkerTask.task_id == "different-request")) is None


async def test_dispatch_rolls_back_queue_and_stage_together(db):  # noqa: F811
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.services.stage_storage.dispatch import dispatch_stage_attempt

    stage, _ = setup_stage(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == stage.task_id))
    attempt, _ = await dispatch_stage_attempt(
        AsyncSessionAdapter(db),
        task=task,
        stage_id=stage.id,
        request_id="roll-back",
        actor_id="u",
        input_snapshot={},
    )
    attempt_id = attempt.id
    db.rollback()
    db.expire_all()
    assert db.get(AiGenerationStage, stage.id).active_attempt_id is None
    assert db.get(AiGenerationAttempt, attempt_id) is None
    assert db.scalar(select(WorkerTask).where(WorkerTask.task_id == "roll-back")) is None
