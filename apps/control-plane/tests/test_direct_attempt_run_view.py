"""Requirement-stage attempts retain the existing public run-detail contract."""

from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db

from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.generation_candidates import RequirementGenerationChain
from testing_agent.repositories.direct_attempt_view import direct_attempt_task_id
from testing_agent.services.stage_storage.history_view import direct_history


async def test_unbound_legacy_attempt_is_not_exposed(db):  # noqa: F811
    seed_task(db)
    db.add(AiGenerationStage(id="stage", task_id="task", stage="interface_extract"))
    db.flush()
    db.add(
        AiGenerationAttempt(
            id="attempt",
            stage_id="stage",
            attempt_no=1,
            operation="generate",
            requested_by="user",
            status="success",
            output_content="old",
        )
    )
    db.commit()
    session = AsyncSessionAdapter(db)
    assert await direct_attempt_task_id(session, "attempt") is None
    assert (await direct_history(session, "task", 1, 20))["total"] == 0


async def test_direct_history_filters_pages_and_keeps_latest_unfiltered(db):  # noqa: F811
    import json
    from datetime import UTC, datetime, timedelta
    from unittest.mock import Mock

    from sqlalchemy import event

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = "r"
    db.add(
        RequirementGenerationChain(
            chain_id="chain", requirement_id="r", kind="function", task_id="task"
        )
    )
    db.add(AiGenerationStage(id="stage", task_id="task", stage="case_names"))
    db.flush()
    now = datetime.now(UTC)
    for index, status in enumerate(("success", "failed", "success"), start=1):
        db.add(
            AiGenerationAttempt(
                id=f"attempt-{index}",
                stage_id="stage",
                attempt_no=index,
                operation="generate",
                requested_by="user",
                status=status,
                output_content=json.dumps({"content": "Y" * 200_000})
                if status == "success"
                else None,
                output_format="json",
                input_snapshot_json={"source": "X" * 200_000},
                error_message="failure" if status == "failed" else "",
                invalidated_reason="",
                created_at=now + timedelta(seconds=index),
            )
        )
    db.commit()
    session = AsyncSessionAdapter(db)
    listener = Mock()
    event.listen(db.bind, "before_cursor_execute", listener)
    try:
        first = await direct_history(session, "task", 1, 2)
        assert listener.call_count <= 5
        older = await direct_history(session, "task", 2, 2)
        filtered = await direct_history(session, "task", 1, 20, "failed")
    finally:
        event.remove(db.bind, "before_cursor_execute", listener)
    assert first["total"] == 3 and first["reviewPendingCount"] == 2
    assert len(json.dumps(first, default=str)) < 30_000
    assert all(
        "input_snapshot_json" not in call.args[2].lower() for call in listener.call_args_list
    )
    assert [item["runId"] for item in first["items"]] == ["attempt-3", "attempt-2"]
    assert older["items"][0]["runId"] == "attempt-1" and older["latestRun"]["runId"] == "attempt-3"
    assert filtered["total"] == 1 and filtered["items"][0]["errorMessage"] == "failure"
    assert filtered["latestRun"]["runId"] == "attempt-3"
