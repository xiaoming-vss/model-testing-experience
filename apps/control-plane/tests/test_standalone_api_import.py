"""Existing API import endpoint can retain independent candidate provenance."""

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
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_collection import ApiCollection
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.api_generate_import import ApiCandidateImporter
from testing_agent.services.standalone_execution import start_standalone_execution
from testing_agent.services.standalone_execution_view import project_standalone_execution


async def test_api_import_rejects_legacy_run_without_writing():
    repository = SimpleNamespace(commit=AsyncMock(), flush=AsyncMock())
    importer = ApiCandidateImporter(
        repository=repository,
        owned_run=AsyncMock(return_value=SimpleNamespace(run_id="old")),
        ensure_collection_access=AsyncMock(),
    )
    with pytest.raises(AppError) as missing:
        await importer.import_api_run("old", "target", True, "user")
    assert missing.value.http_code == 404
    repository.commit.assert_not_awaited()
    repository.flush.assert_not_awaited()


async def test_import_preview_and_confirm_write_source_and_preserve_case_identity(db):  # noqa: F811
    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id, task.task_type = "", "api_case_generate"
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
    execution.workflow_status, execution.current_stage = "success", "completed"
    attempt.status, attempt.review_status = "success", "approved"
    attempt.reviewer_user_id, attempt.reviewed_at = "reviewer", datetime.now(UTC)
    attempt.output_content = "cases:\n  - name: Login\n    method: GET\n    urlTemplate: /new\n"
    attempt.output_format = "yaml"
    target = ApiCollection(collection_id="target", requirement_id="r", name="API")
    db.add(target)
    db.flush()
    db.add(
        ApiCase(
            case_id="existing",
            collection_id="target",
            name="Login",
            method="GET",
            url_template="/old",
        )
    )
    db.commit()
    view = await project_standalone_execution(session, "run")
    importer = ApiCandidateImporter(
        repository=AiGenerateTaskRepository(session),
        owned_run=AsyncMock(return_value=view),
        ensure_collection_access=AsyncMock(),
    )
    preview = await importer.import_api_run("run", "target", False, "user")
    assert preview["requiresConfirmation"] and preview["run"]["importStatus"] == "pending"
    assert target.effective_import_id is None
    assert db.scalar(select(ApiCase).where(ApiCase.case_id == "existing")).url_template == "/old"
    done = await importer.import_api_run("run", "target", True, "user")
    assert not done["requiresConfirmation"] and done["run"]["importStatus"] == "imported"
    assert db.scalar(select(ApiCase).where(ApiCase.case_id == "existing")).url_template == "/new"
    record = db.scalar(select(AiGenerateVersionImport))
    assert record.attempt_id == attempt.id and record.version_id is None
    assert (
        record.changed_case_ids_json == ["existing"]
        and target.effective_import_id == record.import_id
    )
    with pytest.raises(AppError):
        await importer.import_api_run("run", "target", True, "user")


async def test_cross_project_target_does_not_change_formal_cases(db):  # noqa: F811
    from datetime import timedelta

    from testing_agent.models.project import Project
    from testing_agent.models.requirement import Requirement
    from testing_agent.models.sprint import Sprint

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id, task.task_type = "", "api_case_generate"
    now = datetime.now(UTC)
    db.add(Project(project_id="other", user_id="u", name="other"))
    db.flush()
    db.add(
        Sprint(
            sprint_id="other-sprint",
            project_id="other",
            name="s",
            start_time=now,
            end_time=now + timedelta(days=1),
        )
    )
    db.flush()
    db.add(Requirement(requirement_id="other-req", sprint_id="other-sprint", name="r"))
    db.flush()
    db.add(ApiCollection(collection_id="other-target", requirement_id="other-req", name="API"))
    db.flush()
    db.add(
        ApiCase(
            case_id="other-case",
            collection_id="other-target",
            name="Login",
            method="GET",
            url_template="/old",
        )
    )
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
    execution.workflow_status, execution.current_stage = "success", "completed"
    attempt.status, attempt.review_status = "success", "approved"
    attempt.reviewer_user_id, attempt.reviewed_at = "reviewer", now
    attempt.output_content = "cases:\n  - name: Login\n    method: GET\n    urlTemplate: /new\n"
    attempt.output_format = "yaml"
    db.commit()
    view = await project_standalone_execution(session, "run")
    importer = ApiCandidateImporter(
        repository=AiGenerateTaskRepository(session),
        owned_run=AsyncMock(return_value=view),
        ensure_collection_access=AsyncMock(),
    )
    with pytest.raises(AppError):
        await importer.import_api_run("run", "other-target", True, "user")
    db.expire_all()
    assert db.scalar(select(ApiCase).where(ApiCase.case_id == "other-case")).url_template == "/old"
    assert not db.scalars(select(AiGenerateVersionImport)).all()
