"""New stage dispatches record an execution without changing worker identity."""

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db

from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.stage_storage.dispatch import dispatch_stage_attempt


async def test_direct_stage_dispatch_creates_one_execution_and_reuses_it_on_retry(db):  # noqa: F811
    from testing_agent.models.ai_execution import AiExecution

    seed_task(db)
    stage = AiGenerationStage(id="unified-stage", task_id="task", stage="case_names")
    db.add(stage)
    db.commit()
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    session = AsyncSessionAdapter(db)
    attempt, reused = await dispatch_stage_attempt(
        session,
        task=task,
        stage_id=stage.id,
        request_id="request-1",
        actor_id="u",
        input_snapshot={},
    )
    execution = db.get(AiExecution, attempt.execution_id)
    assert not reused
    assert execution is not None and execution.task_id == task.task_id
    assert execution.execution_id != attempt.id
    assert execution.requested_by == "u"
    worker = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "request-1"))
    assert worker.run_id == attempt.id
    retry, reused = await dispatch_stage_attempt(
        session,
        task=task,
        stage_id=stage.id,
        request_id="request-1",
        actor_id="u",
        input_snapshot={},
    )
    assert reused and retry.execution_id == execution.execution_id
    assert len(db.scalars(select(AiExecution)).all()) == 1


async def test_editing_a_candidate_does_not_create_a_worker_execution(db):  # noqa: F811
    from testing_agent.models.ai_execution import AiExecution
    from testing_agent.services.stage_storage import DirectStageStorage

    seed_task(db)
    stage = AiGenerationStage(id="edit-stage", task_id="task", stage="case_names")
    db.add(stage)
    db.commit()
    storage = DirectStageStorage(AsyncSessionAdapter(db))
    original = await storage.prepare(
        stage.id, worker_task_id="worker", requested_by="u", input_snapshot={}
    )
    await storage.publish(
        stage.id,
        attempt_id=original.id,
        worker_task_id="worker",
        content='{"name":"first"}',
        output_format="json",
        output_context=None,
    )
    edited = await storage.save_draft(
        stage.id,
        expected_attempt_id=original.id,
        requested_by="u",
        content='{"name":"edited"}',
        output_format="json",
    )
    assert edited.execution_id is None
    assert len(db.scalars(select(AiExecution)).all()) == 1


async def test_unreviewed_stage_keeps_successful_history_across_runs(db):  # noqa: F811
    from testing_agent.services.stage_storage import DirectStageStorage

    seed_task(db)
    stage = AiGenerationStage(id="aux-stage", task_id="task", stage="generate")
    db.add(stage)
    db.commit()
    storage = DirectStageStorage(AsyncSessionAdapter(db))
    first = await storage.prepare(
        stage.id,
        worker_task_id="worker-1",
        requested_by="u",
        input_snapshot={},
        review_required=False,
    )
    await storage.publish(
        stage.id,
        attempt_id=first.id,
        worker_task_id="worker-1",
        content="first result",
        output_format="text",
        output_context=None,
    )
    assert stage.review_status == "not_required"
    second = await storage.prepare(
        stage.id,
        worker_task_id="worker-2",
        requested_by="u",
        input_snapshot={},
        review_required=False,
    )
    assert first.execution_id != second.execution_id
    assert first.output_content == "first result"
    assert stage.current_attempt_id == first.id
    assert stage.active_attempt_id == second.id


async def test_execution_groups_stages_but_cannot_cross_tasks(db):  # noqa: F811
    from testing_agent.core.errors import AppError
    from testing_agent.models.ai_execution import AiExecution
    from testing_agent.services.stage_storage import DirectStageStorage

    seed_task(db)
    first_stage = AiGenerationStage(id="group-1", task_id="task", stage="stage-1")
    second_stage = AiGenerationStage(id="group-2", task_id="task", stage="stage-2")
    db.add_all([first_stage, second_stage])
    db.commit()
    storage = DirectStageStorage(AsyncSessionAdapter(db))
    first = await storage.prepare(
        first_stage.id, worker_task_id="worker-1", requested_by="u", input_snapshot={}
    )
    second = await storage.prepare(
        second_stage.id,
        worker_task_id="worker-2",
        requested_by="u",
        input_snapshot={},
        execution_id=first.execution_id,
    )
    assert first.execution_id == second.execution_id
    assert len(db.scalars(select(AiExecution)).all()) == 1
    other_task = AiGenerateTask(
        task_id="other-task",
        task_type="code_risk_analysis",
        name="other",
        project_id="p",
        sprint_id="",
        requirement_id="",
        creator_user_id="u",
        source_type="text",
        source_content="",
        instruction="",
    )
    other_execution = AiExecution(
        execution_id="other-execution", task_id="other-task", requested_by="u"
    )
    missing_stage = AiGenerationStage(id="group-3", task_id="task", stage="stage-3")
    db.add(other_task)
    db.flush()
    db.add_all([other_execution, missing_stage])
    db.flush()
    with pytest.raises(AppError):
        await storage.prepare(
            missing_stage.id,
            worker_task_id="worker-3",
            requested_by="u",
            input_snapshot={},
            execution_id="other-execution",
        )


async def test_dispatch_replay_cannot_change_execution_identity(db):  # noqa: F811
    from testing_agent.core.errors import AppError
    from testing_agent.models.ai_execution import AiExecution

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    stage = AiGenerationStage(id="replay-stage", task_id="task", stage="case_names")
    db.add(stage)
    db.commit()
    session = AsyncSessionAdapter(db)
    first, _ = await dispatch_stage_attempt(
        session,
        task=task,
        stage_id=stage.id,
        request_id="same-request",
        actor_id="u",
        input_snapshot={},
    )
    reused, is_replay = await dispatch_stage_attempt(
        session,
        task=task,
        stage_id=stage.id,
        request_id="same-request",
        actor_id="u",
        input_snapshot={},
        execution_id=first.execution_id,
    )
    assert is_replay and reused.id == first.id
    other_execution = AiExecution(execution_id="other", task_id="task", requested_by="u")
    db.add(other_execution)
    db.flush()
    with pytest.raises(AppError):
        await dispatch_stage_attempt(
            session,
            task=task,
            stage_id=stage.id,
            request_id="same-request",
            actor_id="u",
            input_snapshot={},
            execution_id=other_execution.execution_id,
        )


async def test_auxiliary_dispatch_freezes_input_and_replays_without_new_execution(db):  # noqa: F811
    from testing_agent.core.errors import AppError
    from testing_agent.models.ai_execution import AiExecution
    from testing_agent.services.auxiliary_execution import dispatch_auxiliary_execution

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.task_type = "code_risk_analysis"
    db.commit()
    session = AsyncSessionAdapter(db)
    source = {"taskId": "task", "bindings": [{"repositoryId": "original"}]}
    config = {"input": ["original"]}
    first, replay = await dispatch_auxiliary_execution(
        session,
        task=task,
        actor_id="u",
        request_id="request",
        execution_id="execution",
        connection_id="llm",
        source=source,
        config=config,
    )
    source["bindings"][0]["repositoryId"] = "changed"
    config["input"].append("changed")
    assert not replay and first.execution_id == "execution"
    assert first.input_snapshot_json["source"]["bindings"][0]["repositoryId"] == "original"
    assert first.input_snapshot_json["source"]["runId"] == "execution"
    assert first.input_snapshot_json["config"]["input"] == ["original"]
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "request"))
    assert queue.run_id == first.id != first.execution_id
    with pytest.raises(AppError):
        await dispatch_auxiliary_execution(
            session,
            task=task,
            actor_id="u",
            request_id="request",
            execution_id="new-id",
            connection_id="llm",
            source=source,
            config=config,
        )
    again, replay = await dispatch_auxiliary_execution(
        session,
        task=task,
        actor_id="u",
        request_id="request",
        execution_id="new-id",
        connection_id="llm",
        source={"taskId": "task", "bindings": [{"repositoryId": "original"}]},
        config={"input": ["original"]},
    )
    assert replay and again.id == first.id and again.execution_id == "execution"
    assert db.get(AiExecution, "new-id") is None
    assert (
        len(db.scalars(select(AiGenerationStage).where(AiGenerationStage.task_id == "task")).all())
        == 1
    )


async def test_auxiliary_dispatch_rejects_a_cross_project_snapshot(db):  # noqa: F811
    from testing_agent.core.errors import AppError
    from testing_agent.models.ai_execution import AiExecution
    from testing_agent.services.auxiliary_execution import dispatch_auxiliary_execution

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.task_type = "code_risk_analysis"
    db.commit()
    with pytest.raises(AppError):
        await dispatch_auxiliary_execution(
            AsyncSessionAdapter(db),
            task=task,
            actor_id="u",
            request_id="request",
            execution_id="execution",
            connection_id="llm",
            source={"projectId": "other"},
            config={},
        )
    assert db.get(AiExecution, "execution") is None


@pytest.mark.parametrize("connection_id", ["personal-llm", "personal-gitlab"])
async def test_direct_execution_is_retired_in_revocation_transaction(
    db,  # noqa: F811
    monkeypatch,
    connection_id,
):
    from unittest.mock import AsyncMock

    from testing_agent.services.stage_storage import DirectStageStorage
    from testing_agent.services.worker_authorization import revoke_executions

    seed_task(db)
    stage = AiGenerationStage(id="revocation-stage", task_id="task", stage="case_names")
    db.add(stage)
    db.commit()
    storage = DirectStageStorage(AsyncSessionAdapter(db))
    attempt = await storage.prepare(
        stage.id,
        worker_task_id="direct-worker",
        requested_by="u",
        input_snapshot={
            "llmConnectionId": "personal-llm",
            "source": {"bindings": [{"connectionId": "personal-gitlab"}]},
            "config": {},
        },
    )
    queue = WorkerTask(
        domain="ai",
        task_id="direct-worker",
        task_type="functional_case_generate",
        run_id=attempt.id,
        status="pending",
    )
    db.add(queue)
    db.commit()
    monkeypatch.setattr(
        "testing_agent.services.integration_lifecycle.revoke_integrations", AsyncMock()
    )
    session = AsyncSessionAdapter(db)
    await revoke_executions(session, actor="u", connection_id="unrelated")
    assert queue.status == attempt.status == "pending"
    await revoke_executions(session, actor="u", connection_id=connection_id)
    assert queue.status == attempt.status == "failed"
    assert stage.active_attempt_id is None
    assert attempt.error_message
    db.rollback()
    assert queue.status == attempt.status == "pending"
    assert stage.active_attempt_id == attempt.id
    await revoke_executions(session, actor="u", connection_id=connection_id)
    db.commit()
    assert queue.status == attempt.status == "failed"
