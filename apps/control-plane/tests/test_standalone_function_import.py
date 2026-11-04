"""Independent functional imports require and preserve their chosen target."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db
from support.direct_graph import cases_output

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.function_generate_import import import_function_run
from testing_agent.services.standalone_execution import start_standalone_execution
from testing_agent.services.standalone_execution_view import project_standalone_execution


async def test_function_import_rejects_legacy_run_without_writing():
    repository = SimpleNamespace(commit=AsyncMock(), flush=AsyncMock())
    access = SimpleNamespace(
        repository=repository, owned_run=AsyncMock(return_value=SimpleNamespace(run_id="old"))
    )
    with pytest.raises(AppError) as missing:
        await import_function_run(access, "old", True, "user", target_requirement_id="r")
    assert missing.value.http_code == 404
    repository.commit.assert_not_awaited()
    repository.flush.assert_not_awaited()


async def test_function_import_uses_chosen_requirement_and_preserves_conflict_identity(db):  # noqa: F811
    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    execution, attempt, _ = await start_standalone_execution(
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
    db.get(AiGenerationStage, attempt.stage_id).stage = "detailed_cases"
    execution.workflow_status, execution.current_stage = "success", "completed"
    attempt.status, attempt.review_status = "success", "approved"
    attempt.reviewer_user_id, attempt.reviewed_at = "reviewer", datetime.now(UTC)
    attempt.output_content, attempt.output_format = cases_output(), "json"
    suite = FunctionTestSuite(suite_id="target", requirement_id="r", name="任务管理")
    db.add(suite)
    db.flush()
    db.add(FunctionTestCase(case_id="existing", suite_id="target", title="用例1"))
    db.commit()
    view = await project_standalone_execution(session, "run")
    access = SimpleNamespace(
        repository=AiGenerateTaskRepository(session),
        owned_run=AsyncMock(return_value=view),
        ensure_requirement_access=AsyncMock(),
    )
    with pytest.raises(AppError):
        await import_function_run(access, "run", False, "user")
    preview = await import_function_run(access, "run", False, "user", target_requirement_id="r")
    assert preview["requiresConfirmation"] and preview["run"]["importStatus"] == "pending"
    assert len(db.scalars(select(FunctionTestCase)).all()) == 1
    result = await import_function_run(access, "run", True, "user", target_requirement_id="r")
    assert not result["requiresConfirmation"] and result["run"]["importStatus"] == "imported"
    assert result["run"]["requirementId"] == ""
    cases = db.scalars(select(FunctionTestCase).where(FunctionTestCase.suite_id == "target")).all()
    assert len(cases) == 3 and any(
        case.case_id == "existing" and case.title == "用例1" for case in cases
    )
    record = db.scalar(select(AiGenerateVersionImport))
    assert record.attempt_id == attempt.id and suite.effective_import_id == record.import_id
    with pytest.raises(AppError):
        await import_function_run(access, "run", True, "user", target_requirement_id="r")
