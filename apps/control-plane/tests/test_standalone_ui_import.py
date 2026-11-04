"""Independent UI import uses existing conflict handling and source records."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.standalone_execution import start_standalone_execution
from testing_agent.services.standalone_execution_view import project_standalone_execution
from testing_agent.services.ui_generate_import import import_ui_run


async def test_ui_import_rejects_legacy_runs_without_writing():
    repository = SimpleNamespace(get_run_for_update=AsyncMock(), commit=AsyncMock())
    context = SimpleNamespace(
        repository=repository, owned_run=AsyncMock(return_value=SimpleNamespace(run_id="old"))
    )
    with pytest.raises(AppError) as missing:
        await import_ui_run(context, "old", "target", True, "user")
    assert missing.value.http_code == 404
    repository.get_run_for_update.assert_not_awaited()
    repository.commit.assert_not_awaited()


async def test_ui_import_records_approved_candidate_and_handles_conflict(db):  # noqa: F811
    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id, task.task_type = "", "ui_case_generate"
    db.commit()
    session = AsyncSessionAdapter(db)
    execution, attempt, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="run",
        request_id="worker",
        actor_id="user",
        connection_id="llm",
        source={"uiWorkflowVersion": "ui_three_stage/1.0"},
        config={},
        checkpoint_enabled=True,
    )
    db.get(AiGenerationStage, attempt.stage_id).stage = "ui_yaml"
    execution.workflow_status, execution.current_stage = "success", "completed"
    attempt.status, attempt.review_status = "success", "approved"
    attempt.reviewer_user_id, attempt.reviewed_at = "reviewer", datetime.now(UTC)
    attempt.output_content = """- name: Login
  enabled: true
  orderNo: 1
  stepsJson:
  - orderNo: 1
    stepName: Open
    keyword: open
    operationValue: https://example.test/new
    continueOnFailure: false
    enabled: true
"""
    attempt.output_format = "yaml"
    target = UiTestSuite(suite_id="target", requirement_id="r", name="UI")
    db.add(target)
    db.flush()
    db.add(UiTestCase(case_id="existing", suite_id="target", name="Login", steps_json=[]))
    db.commit()
    view = await project_standalone_execution(session, "run")
    context = SimpleNamespace(
        repository=AiGenerateTaskRepository(session),
        owned_run=AsyncMock(return_value=view),
        ensure_requirement_access=AsyncMock(),
    )
    preview = await import_ui_run(context, "run", "target", False, "user")
    assert preview["requiresConfirmation"] and preview["run"]["importStatus"] == "pending"
    assert db.scalar(select(UiTestCase).where(UiTestCase.case_id == "existing")).steps_json == []
    result = await import_ui_run(context, "run", "target", True, "user")
    assert not result["requiresConfirmation"] and result["run"]["importStatus"] == "imported"
    assert (
        db.scalar(select(UiTestCase).where(UiTestCase.case_id == "existing")).steps_json[0][
            "operationValue"
        ]
        == "https://example.test/new"
    )
    record = db.scalar(select(AiGenerateVersionImport))
    assert record.attempt_id == attempt.id and target.effective_import_id == record.import_id
    with pytest.raises(AppError):
        await import_ui_run(context, "run", "target", True, "user")
