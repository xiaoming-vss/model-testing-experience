"""Independent execution history is bounded and keeps run state isolated."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db

from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.schemas.ai_generate_task import AiGenerateRunHistoryResponse
from testing_agent.services.standalone_execution import start_standalone_execution
from testing_agent.services.standalone_history import standalone_history


async def test_paginated_history_filters_and_does_not_mix_candidates(db):  # noqa: F811
    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    now = datetime.now(UTC)
    attempts = []
    for index, status in enumerate(("success", "success", "failed"), start=1):
        execution, attempt, _ = await start_standalone_execution(
            session,
            task=task,
            execution_id=f"run-{index}",
            request_id=f"worker-{index}",
            actor_id="user",
            connection_id="llm",
            source={},
            config={},
            checkpoint_enabled=False,
        )
        execution.workflow_status, execution.current_stage = (
            status,
            "completed" if status == "success" else "detailed_cases",
        )
        execution.created_at = now + timedelta(seconds=index)
        attempt.status, attempt.output_content, attempt.output_format = (
            status,
            f"result-{index}",
            "text",
        )
        attempt.review_status = "approved" if index == 2 else "pending"
        if index == 3:
            attempt.error_message = "failure from run 3"
        attempts.append(attempt)
    db.get(AiGenerationStage, attempts[0].stage_id).stage = "detailed_cases"
    db.add(
        AiGenerateVersionImport(
            import_id="source",
            task_id="task",
            version_id=None,
            attempt_id=attempts[1].id,
            leaf_stage="detailed_cases",
            target_type="function_suite",
            target_id="target",
            target_case_count=1,
            mixed_source=False,
            reviewer_user_id="reviewer",
            review_comment="",
            imported_by="user",
            imported_at=now,
        )
    )
    db.commit()
    first = await standalone_history(session, "task", 1, 2)
    AiGenerateRunHistoryResponse.model_validate(first)
    assert first["total"] == 3 and first["statusCounts"] == {"success": 2, "failed": 1}
    assert [item["runId"] for item in first["items"]] == ["run-3", "run-2"]
    assert first["items"][0]["errorMessage"] == "failure from run 3"
    assert first["items"][1]["importedTargets"] == [
        {"targetType": "function_suite", "targetId": "target"}
    ]
    assert first["latestRun"]["runId"] == "run-3" and first["reviewPendingCount"] == 1
    page = await standalone_history(session, "task", 2, 2)
    assert [item["runId"] for item in page["items"]] == ["run-1"]
    assert page["latestRun"]["runId"] == "run-3"
    for selection, expected in (
        ("imported", "run-2"),
        ("failed", "run-3"),
        ("review_pending", "run-1"),
    ):
        filtered = await standalone_history(session, "task", 1, 20, selection)
        assert [item["runId"] for item in filtered["items"]] == [expected]


async def test_running_revision_on_approved_stage_is_filtered_as_running(db):  # noqa: F811
    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    now = datetime.now(UTC)
    execution, attempt, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="run-running",
        request_id="worker-running",
        actor_id="user",
        connection_id="llm",
        source={},
        config={},
        checkpoint_enabled=False,
    )
    stage = db.get(AiGenerationStage, attempt.stage_id)
    stage.stage = "detailed_cases"
    execution.workflow_status, execution.current_stage = "pending", "detailed_cases"
    attempt.status, attempt.output_content, attempt.output_format = "success", "result", "text"
    attempt.review_status = "approved"
    db.add(
        AiGenerationAttempt(
            id="attempt-revision",
            stage_id=stage.id,
            execution_id=execution.execution_id,
            attempt_no=attempt.attempt_no + 1,
            operation="revise",
            requested_by="user",
            input_snapshot_json={},
            status="pending",
            invalidated_reason="",
            created_at=now,
        )
    )
    db.commit()
    running = await standalone_history(session, "task", 1, 20, "running")
    assert [item["runId"] for item in running["items"]] == ["run-running"]
    assert running["items"][0]["reviewStatus"] == "approved"
    import_pending = await standalone_history(session, "task", 1, 20, "import_pending")
    assert import_pending["items"] == []
