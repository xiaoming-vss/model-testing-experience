"""Independent executions keep their attempts and review state isolated."""

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db

from testing_agent.core.errors import AppError
from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.standalone_execution import start_standalone_execution


async def test_task_delete_rejects_active_independent_execution(db):  # noqa: F811
    from unittest.mock import AsyncMock

    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.services.ai_task_commands import GenerationTaskCommands
    from testing_agent.services.ai_task_scope import GenerationAccess

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    await start_standalone_execution(
        session,
        task=task,
        execution_id="active-run",
        request_id="active-worker",
        actor_id="u",
        connection_id="llm",
        source={},
        config={},
        checkpoint_enabled=False,
    )
    db.commit()
    repository = AiGenerateTaskRepository(session)
    deletion = AsyncMock()
    commands = GenerationTaskCommands(
        repository, None, GenerationAccess(repository), deletion=deletion
    )
    with pytest.raises(AppError):
        await commands.delete("function", "task", "u")
    deletion.delete.assert_not_awaited()
    assert db.get(AiExecution, "active-run") is not None


async def test_task_delete_rejects_changed_scope_after_authorization(db):  # noqa: F811
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.services.ai_task_commands import GenerationTaskCommands

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    authorized = SimpleNamespace(
        project_id="different-project",
        sprint_id=task.sprint_id,
        requirement_id="",
        order_id=task.order_id,
        task_type=task.task_type,
    )
    access = SimpleNamespace(
        owned_task=AsyncMock(return_value=authorized), validate_task_scope=AsyncMock()
    )
    deletion = AsyncMock()
    commands = GenerationTaskCommands(
        AiGenerateTaskRepository(AsyncSessionAdapter(db)), None, access, deletion=deletion
    )
    with pytest.raises(AppError) as missing:
        await commands.delete("function", "task", "u")
    assert missing.value.http_code == 404
    deletion.delete.assert_not_awaited()


async def test_independent_runs_share_stage_identity_not_active_or_review_state(db):  # noqa: F811
    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    source = {"sourceContent": "original", "runId": "first"}
    first, attempt1, reused = await start_standalone_execution(
        session,
        task=task,
        execution_id="first",
        request_id="worker-1",
        actor_id="u",
        connection_id="llm",
        source=source,
        config={"mode": "first"},
        checkpoint_enabled=True,
    )
    source["sourceContent"] = "changed"
    second, attempt2, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="second",
        request_id="worker-2",
        actor_id="u",
        connection_id="llm",
        source={"sourceContent": "second", "runId": "second"},
        config={"mode": "second"},
        checkpoint_enabled=True,
    )
    assert not reused and first.execution_id != second.execution_id
    assert first.source_snapshot_json["sourceContent"] == "original"
    assert attempt1.input_snapshot_json["source"]["sourceContent"] == "original"
    assert attempt2.input_snapshot_json["source"]["sourceContent"] == "second"
    assert attempt1.stage_id == attempt2.stage_id
    assert (attempt1.attempt_no, attempt2.attempt_no) == (1, 2)
    assert attempt1.id != first.execution_id and attempt2.id != second.execution_id
    stage = db.get(AiGenerationStage, attempt1.stage_id)
    assert stage.active_attempt_id is None and stage.current_attempt_id is None
    attempt1.status = "success"
    attempt1.review_status = "approved"
    attempt1.reviewer_user_id = "reviewer"
    db.flush()
    assert attempt2.status == "pending" and attempt2.review_status == "pending"
    assert attempt2.reviewer_user_id is None
    queues = list(
        db.scalars(select(WorkerTask).where(WorkerTask.task_id.in_(["worker-1", "worker-2"])))
    )
    assert {queue.run_id for queue in queues} == {attempt1.id, attempt2.id}


async def test_independent_request_replay_is_bound_to_actor_and_frozen_input(db):  # noqa: F811
    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    values = dict(
        task=task,
        request_id="same-request",
        actor_id="u",
        connection_id="llm",
        source={"sourceContent": "fixed"},
        config={"input": 1},
        checkpoint_enabled=False,
    )
    first, attempt, _ = await start_standalone_execution(session, execution_id="first", **values)
    replay, same_attempt, reused = await start_standalone_execution(
        session, execution_id="new-generated-id", **values
    )
    assert reused and replay.execution_id == first.execution_id and same_attempt.id == attempt.id
    assert db.get(AiExecution, "new-generated-id") is None
    for altered in (
        {"actor_id": "someone-else"},
        {"config": {"input": 2}},
        {"connection_id": "other"},
    ):
        with pytest.raises(AppError):
            await start_standalone_execution(
                session, execution_id="another", **{**values, **altered}
            )
    assert len(db.scalars(select(AiGenerationAttempt)).all()) == 1


async def test_independent_projection_never_mixes_other_execution_artifacts(db):  # noqa: F811
    from testing_agent.schemas.ai_generate_task import AiGenerateTaskRunResponse
    from testing_agent.services.ai_task_output import dump_run
    from testing_agent.services.standalone_execution_view import project_standalone_execution

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    first, initial1, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="first",
        request_id="worker-1",
        actor_id="u",
        connection_id="llm",
        source={"sourceContent": "source-one"},
        config={},
        checkpoint_enabled=True,
    )
    second, initial2, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="second",
        request_id="worker-2",
        actor_id="u",
        connection_id="llm",
        source={"sourceContent": "source-two"},
        config={},
        checkpoint_enabled=True,
    )
    for attempt, text in ((initial1, "one"), (initial2, "two")):
        attempt.status = "success"
        attempt.output_content = f'{{"requirement":"{text}"}}'
        attempt.output_format = "json"
    names = AiGenerationStage(id="standalone-names", task_id="task", stage="case_names")
    final = AiGenerationStage(id="standalone-final", task_id="task", stage="detailed_cases")
    db.add_all([names, final])
    db.flush()
    for number, execution in enumerate((first, second), 1):
        db.add(
            AiGenerationAttempt(
                id=f"names-{number}",
                stage_id=names.id,
                execution_id=execution.execution_id,
                attempt_no=number,
                operation="generate",
                status="success",
                requested_by="u",
                input_snapshot_json={"config": {}, "source": {}},
                output_content=f'{{"points":["{number}"]}}',
                output_format="json",
                invalidated_reason="",
                review_status="pending",
            )
        )
    db.add(
        AiGenerationAttempt(
            id="final-first",
            stage_id=final.id,
            execution_id=first.execution_id,
            attempt_no=1,
            operation="generate",
            status="success",
            requested_by="u",
            input_snapshot_json={"config": {}, "source": {}},
            output_content="first result",
            output_format="text",
            invalidated_reason="",
            review_status="approved",
            reviewer_user_id="reviewer",
            review_comment="accepted",
        )
    )
    first.workflow_status, first.current_stage = "success", "completed"
    second.workflow_status, second.current_stage = "waiting_review", "case_names"
    db.commit()
    projected_first = await project_standalone_execution(session, "first")
    projected_second = await project_standalone_execution(session, "second")
    first_payload, second_payload = dump_run(projected_first), dump_run(projected_second)
    AiGenerateTaskRunResponse.model_validate(first_payload)
    AiGenerateTaskRunResponse.model_validate(second_payload)
    assert first_payload["snapshotJson"]["sourceContent"] == "source-one"
    assert first_payload["configJson"]["requirementAnalysis"] == {"requirement": "one"}
    assert first_payload["configJson"]["caseNames"] == {"points": ["1"]}
    assert first_payload["resultYaml"] == "first result"
    assert first_payload["reviewerUserId"] == "reviewer"
    assert second_payload["snapshotJson"]["sourceContent"] == "source-two"
    assert second_payload["configJson"]["requirementAnalysis"] == {"requirement": "two"}
    assert second_payload["configJson"]["caseNames"] == {"points": ["2"]}
    assert second_payload["resultYaml"] == "" and second_payload["reviewStatus"] == "pending"


async def test_independent_edit_and_review_are_scoped_to_their_execution(db):  # noqa: F811
    from testing_agent.services.standalone_candidate import (
        review_standalone_candidate,
        save_standalone_draft,
    )
    from testing_agent.services.standalone_execution_view import project_standalone_execution

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id, task.task_type = "", "api_case_generate"
    db.commit()
    session = AsyncSessionAdapter(db)
    executions, attempts = [], []
    for number in (1, 2):
        execution, attempt, _ = await start_standalone_execution(
            session,
            task=task,
            execution_id=f"run-{number}",
            request_id=f"worker-{number}",
            actor_id="u",
            connection_id="llm",
            source={"sourceContent": f"source-{number}"},
            config={},
            checkpoint_enabled=False,
        )
        execution.workflow_status, execution.current_stage = "success", "completed"
        attempt.status, attempt.output_content, attempt.output_format = (
            "success",
            f"original-{number}",
            "text",
        )
        queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == f"worker-{number}"))
        queue.status = "success"
        executions.append(execution)
        attempts.append(attempt)
    db.commit()
    edited = await save_standalone_draft(
        session,
        task=task,
        execution_id="run-1",
        stage_name="generate",
        expected_attempt_id=attempts[0].id,
        actor_id="editor",
        content="edited-1",
        output_format="text",
    )
    assert edited.execution_id == "run-1" and edited.worker_task_id is None
    assert edited.input_snapshot_json["editBaseAttemptId"] == attempts[0].id
    assert attempts[0].output_content == "original-1"
    assert len(db.scalars(select(WorkerTask)).all()) == 2
    assert len(db.scalars(select(AiExecution)).all()) == 2
    with pytest.raises(AppError):
        await review_standalone_candidate(
            session,
            task=task,
            execution_id="run-1",
            stage_name="generate",
            expected_attempt_id=attempts[0].id,
            actor_id="reviewer",
            approved=True,
            comment="stale",
        )
    await review_standalone_candidate(
        session,
        task=task,
        execution_id="run-2",
        stage_name="generate",
        expected_attempt_id=attempts[1].id,
        actor_id="reviewer-2",
        approved=True,
        comment="two",
    )
    assert edited.review_status == "pending" and attempts[1].reviewer_user_id == "reviewer-2"
    await review_standalone_candidate(
        session,
        task=task,
        execution_id="run-1",
        stage_name="generate",
        expected_attempt_id=edited.id,
        actor_id="reviewer-1",
        approved=True,
        comment="one",
    )
    first = await project_standalone_execution(session, "run-1")
    second = await project_standalone_execution(session, "run-2")
    assert (first.result_yaml, first.reviewer_user_id) == ("edited-1", "reviewer-1")
    assert (second.result_yaml, second.reviewer_user_id) == ("original-2", "reviewer-2")


async def test_checkpoint_advance_retry_and_revision_keep_execution_identity(db):  # noqa: F811
    from testing_agent.services.standalone_candidate import review_standalone_candidate
    from testing_agent.services.standalone_dispatch import enqueue_standalone_attempt

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    execution, first, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="run",
        request_id="worker-1",
        actor_id="u",
        connection_id="llm",
        source={"sourceContent": "frozen"},
        config={},
        checkpoint_enabled=True,
    )
    first.status, first.output_content, first.output_format = (
        "success",
        '{"name":"analysis"}',
        "json",
    )
    execution.workflow_status = "waiting_review"
    db.scalar(select(WorkerTask).where(WorkerTask.task_id == "worker-1")).status = "success"
    db.commit()
    await review_standalone_candidate(
        session,
        task=task,
        execution_id="run",
        stage_name="requirement_analysis",
        expected_attempt_id=first.id,
        actor_id="reviewer",
        approved=True,
        comment="ok",
    )
    second, replay = await enqueue_standalone_attempt(
        session,
        task=task,
        execution_id="run",
        request_id="worker-2",
        actor_id="u",
        connection_id="llm",
        stage_name="case_names",
        operation="advance",
        expected_attempt_id=first.id,
        config={"requirementAnalysis": {"name": "analysis"}},
    )
    assert not replay and second.execution_id == first.execution_id == "run"
    assert second.operation == "generate" and second.review_status == "pending"
    assert second.input_snapshot_json["baseAttemptId"] == first.id
    assert execution.current_stage == "case_names" and execution.workflow_status == "pending"
    same, replay = await enqueue_standalone_attempt(
        session,
        task=task,
        execution_id="run",
        request_id="worker-2",
        actor_id="u",
        connection_id="llm",
        stage_name="case_names",
        operation="advance",
        expected_attempt_id=first.id,
        config={"requirementAnalysis": {"name": "analysis"}},
    )
    assert replay and same.id == second.id
    second.status, second.error_message = "failed", "model failure"
    execution.workflow_status = "failed"
    db.scalar(select(WorkerTask).where(WorkerTask.task_id == "worker-2")).status = "failed"
    db.commit()
    retried, _ = await enqueue_standalone_attempt(
        session,
        task=task,
        execution_id="run",
        request_id="worker-3",
        actor_id="other-user",
        connection_id="other-llm",
        stage_name="case_names",
        operation="retry",
        expected_attempt_id=second.id,
    )
    assert retried.execution_id == "run" and retried.operation == "retry"
    assert retried.requested_by == "other-user"
    assert retried.input_snapshot_json["source"]["sourceContent"] == "frozen"
    assert retried.input_snapshot_json["config"] == second.input_snapshot_json["config"]
    assert retried.input_snapshot_json["llmConnectionId"] == "other-llm"
    retried.status, retried.output_content, retried.output_format = (
        "success",
        '{"points":["one"]}',
        "json",
    )
    execution.workflow_status = "waiting_review"
    db.scalar(select(WorkerTask).where(WorkerTask.task_id == "worker-3")).status = "success"
    db.commit()
    with pytest.raises(AppError):
        await enqueue_standalone_attempt(
            session,
            task=task,
            execution_id="run",
            request_id="foreign-input",
            actor_id="u",
            connection_id="llm",
            stage_name="case_names",
            operation="revise",
            expected_attempt_id=retried.id,
            config={"requirementAnalysis": {"name": "other execution"}},
            revision_instruction="add coverage",
        )
    revised, _ = await enqueue_standalone_attempt(
        session,
        task=task,
        execution_id="run",
        request_id="worker-4",
        actor_id="u",
        connection_id="llm",
        stage_name="case_names",
        operation="revise",
        expected_attempt_id=retried.id,
        config={"caseNames": {"points": ["one"]}},
        revision_instruction="add coverage",
    )
    assert revised.operation == "revise" and revised.revision_instruction == "add coverage"
    assert revised.input_snapshot_json["currentOutput"] == retried.output_content
    assert revised.input_snapshot_json["baseAttemptId"] == retried.id
    assert revised.input_snapshot_json["config"]["requirementAnalysis"] == {"name": "analysis"}
    replayed, reused = await enqueue_standalone_attempt(
        session,
        task=task,
        execution_id="run",
        request_id="worker-4",
        actor_id="u",
        connection_id="llm",
        stage_name="case_names",
        operation="revise",
        expected_attempt_id=retried.id,
        config={"caseNames": {"points": ["one"]}},
        revision_instruction="add coverage",
    )
    assert reused and replayed.id == revised.id
    assert first.review_status == "approved" and first.review_comment == "ok"
    assert len(db.scalars(select(AiExecution)).all()) == 1
    revised.status = "failed"
    execution.workflow_status = "failed"
    db.scalar(select(WorkerTask).where(WorkerTask.task_id == "worker-4")).status = "failed"
    db.commit()
    retry_revision, _ = await enqueue_standalone_attempt(
        session,
        task=task,
        execution_id="run",
        request_id="worker-5",
        actor_id="u",
        connection_id="llm",
        stage_name="case_names",
        operation="retry",
        expected_attempt_id=revised.id,
    )
    assert retry_revision.revision_instruction == "add coverage"
    replay_revision, reused = await enqueue_standalone_attempt(
        session,
        task=task,
        execution_id="run",
        request_id="worker-5",
        actor_id="u",
        connection_id="llm",
        stage_name="case_names",
        operation="retry",
        expected_attempt_id=revised.id,
    )
    assert reused and replay_revision.id == retry_revision.id


async def test_checkpoint_cannot_advance_without_current_approval(db):  # noqa: F811
    from testing_agent.services.standalone_dispatch import enqueue_standalone_attempt

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    execution, first, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="run",
        request_id="worker-1",
        actor_id="u",
        connection_id="llm",
        source={},
        config={},
        checkpoint_enabled=True,
    )
    first.status, first.output_content = "success", '{"name":"analysis"}'
    execution.workflow_status = "waiting_review"
    db.scalar(select(WorkerTask).where(WorkerTask.task_id == "worker-1")).status = "success"
    db.commit()
    with pytest.raises(AppError):
        await enqueue_standalone_attempt(
            session,
            task=task,
            execution_id="run",
            request_id="worker-2",
            actor_id="u",
            connection_id="llm",
            stage_name="case_names",
            operation="advance",
            expected_attempt_id=first.id,
            config={},
        )
    assert len(db.scalars(select(WorkerTask)).all()) == 1


async def test_independent_function_snapshot_uses_its_own_source(db):  # noqa: F811
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.services.ai_task_output import build_generate_run_snapshot

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    task.source_content = "independent requirement"
    db.commit()
    snapshot = await build_generate_run_snapshot(
        AiGenerateTaskRepository(AsyncSessionAdapter(db)), "function", task, "run"
    )
    assert snapshot["sourceContent"] == "independent requirement"
    assert "requirementUnderstandingVersion" not in snapshot
