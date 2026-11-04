"""Requirement-stage attempts retain the existing public run-detail contract."""

from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db

from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.repositories.direct_attempt_view import direct_attempt_task_id
from testing_agent.schemas.ai_generate_task import (
    AiGenerateRunHistoryResponse,
    AiGenerateTaskRunResponse,
)
from testing_agent.services.stage_storage.history_view import direct_history
from testing_agent.services.stage_storage.run_view import direct_attempt_view


async def test_direct_detail_keeps_immutable_version_and_import_provenance(db):  # noqa: F811
    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.task_type, task.requirement_id = "api_case_generate", "requirement"
    stage = AiGenerationStage(id="stage", task_id="task", stage="openapi_extract")
    db.add(stage)
    db.flush()
    attempt = AiGenerationAttempt(
        id="attempt",
        stage_id="stage",
        attempt_no=1,
        operation="generate",
        requested_by="user",
        status="success",
        output_content='{"path":"draft"}',
        output_format="json",
        input_snapshot_json={"source": {"sourceContent": "frozen"}, "config": {}},
        invalidated_reason="",
    )
    db.add(attempt)
    db.flush()
    version = AiGenerateStageVersion(
        version_id="version",
        task_id="task",
        stage="openapi_extract",
        version_no=1,
        attempt_id="attempt",
        artifact_content='{"path":"approved"}',
        artifact_format="json",
        reviewer_user_id="reviewer",
        review_comment="approved",
    )
    db.add(version)
    db.flush()
    db.add(
        AiGenerateVersionImport(
            import_id="source",
            task_id="task",
            version_id="version",
            leaf_stage="openapi_extract",
            target_type="api_collection",
            target_id="target",
            imported_by="user",
            imported_at=attempt.created_at,
        )
    )
    db.commit()
    session = AsyncSessionAdapter(db)
    assert await direct_attempt_task_id(session, "attempt") == "task"
    result = await direct_attempt_view(session, "task", "attempt")
    AiGenerateTaskRunResponse.model_validate(result)
    assert result["runId"] == "attempt" and result["generationChainManaged"] is True
    assert result["configJson"]["apiExtraction"] == {"path": "approved"}
    assert result["snapshotJson"]["sourceContent"] == "frozen"
    assert result["reviewStatus"] == "approved" and result["reviewerUserId"] == "reviewer"
    assert result["importedTargets"] == [{"targetType": "api_collection", "targetId": "target"}]
    history = await direct_history(session, "task", 1, 20)
    AiGenerateRunHistoryResponse.model_validate(history)
    assert history["total"] == 1 and history["items"][0]["runId"] == "attempt"
    assert history["items"][0]["importStatus"] == "imported"
    assert history["items"][0]["availableArtifacts"] == ["apiExtraction"]
    assert (await direct_history(session, "task", 1, 20, "imported"))["total"] == 1
    assert (await direct_history(session, "task", 1, 20, "failed"))["total"] == 0
    task.requirement_id = ""
    db.commit()
    assert await direct_attempt_task_id(session, "attempt") is None


async def test_direct_history_filters_pages_and_keeps_latest_unfiltered(db):  # noqa: F811
    import json
    from datetime import UTC, datetime, timedelta
    from unittest.mock import Mock

    from sqlalchemy import event

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = "requirement"
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
        assert listener.call_count <= 4
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
