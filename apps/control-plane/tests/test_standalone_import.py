"""Independent imports preserve asset ownership and reviewed provenance."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.services.standalone_execution import start_standalone_execution
from testing_agent.services.standalone_execution_view import project_standalone_execution
from testing_agent.services.standalone_import import ImportChange, record_standalone_import


async def test_record_approved_candidate_provenance_without_changing_formal_cases(db):  # noqa: F811
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
    stage = db.get(AiGenerationStage, attempt.stage_id)
    stage.stage = "detailed_cases"
    execution.workflow_status, execution.current_stage = "success", "completed"
    attempt.status, attempt.output_content, attempt.output_format = (
        "success",
        '{"cases":[]}',
        "json",
    )
    attempt.review_status, attempt.reviewer_user_id = "approved", "reviewer"
    attempt.reviewed_at, attempt.review_comment = datetime.now(UTC), "ready"
    suite = FunctionTestSuite(suite_id="suite", requirement_id="r", name="module")
    db.add(suite)
    db.flush()
    db.add_all(
        [
            FunctionTestCase(case_id="changed", suite_id="suite", title="changed"),
            FunctionTestCase(case_id="unchanged", suite_id="suite", title="unchanged"),
        ]
    )
    db.commit()
    changes = [ImportChange("function_suite", "suite", ("changed",))]
    records = await record_standalone_import(
        session,
        task=task,
        execution_id=execution.execution_id,
        attempt_id=attempt.id,
        actor_id="importer",
        changes=changes,
    )
    assert len(records) == 1
    record = records[0]
    assert record.version_id is None and record.attempt_id == attempt.id
    assert record.reviewer_user_id == "reviewer" and record.imported_by == "importer"
    assert record.target_case_count == 2 and record.mixed_source
    assert record.changed_case_ids_json == ["changed"]
    assert suite.effective_import_id == record.import_id
    view = await project_standalone_execution(session, execution.execution_id)
    assert view.import_status == "imported"
    assert view.imported_targets == [{"targetType": "function_suite", "targetId": "suite"}]
    assert (
        len(db.scalars(select(FunctionTestCase).where(FunctionTestCase.suite_id == "suite")).all())
        == 2
    )

    # A forged changed-case ID must not create a record or alter the target pointer.
    prior = suite.effective_import_id
    with pytest.raises(AppError):
        await record_standalone_import(
            session,
            task=task,
            execution_id=execution.execution_id,
            attempt_id=attempt.id,
            actor_id="importer",
            changes=[ImportChange("function_suite", "suite", ("not-in-suite",))],
        )
    assert suite.effective_import_id == prior
    assert len(db.scalars(select(AiGenerateVersionImport)).all()) == 1
    with pytest.raises(AppError):
        await record_standalone_import(
            session,
            task=task,
            execution_id=execution.execution_id,
            attempt_id=attempt.id,
            actor_id="importer",
            changes=[
                ImportChange("function_suite", "suite", ("changed",)),
                ImportChange("function_suite", "zz-missing", ()),
            ],
        )
    assert suite.effective_import_id == prior
    assert len(db.scalars(select(AiGenerateVersionImport)).all()) == 1

    attempt.review_status = "pending"
    db.flush()
    with pytest.raises(AppError):
        await record_standalone_import(
            session,
            task=task,
            execution_id=execution.execution_id,
            attempt_id=attempt.id,
            actor_id="importer",
            changes=changes,
        )

    from testing_agent.repositories.deletion import delete_owned_data

    await delete_owned_data(session, task)
    db.commit()
    db.expire_all()
    target = db.scalar(select(FunctionTestSuite).where(FunctionTestSuite.suite_id == "suite"))
    assert target.effective_import_id is None
    assert (
        len(db.scalars(select(FunctionTestCase).where(FunctionTestCase.suite_id == "suite")).all())
        == 2
    )


async def test_delete_imported_execution_keeps_assets_and_only_clears_its_pointer(db):  # noqa: F811
    from testing_agent.models.ai_execution import AiExecution
    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.services.standalone_execution_delete import delete_standalone_execution

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
    stage = db.get(AiGenerationStage, attempt.stage_id)
    stage.stage = "detailed_cases"
    execution.workflow_status, execution.current_stage = "success", "completed"
    attempt.status, attempt.output_content, attempt.output_format = (
        "success",
        '{"cases":[]}',
        "json",
    )
    attempt.review_status, attempt.reviewer_user_id = "approved", "reviewer"
    attempt.reviewed_at = datetime.now(UTC)
    suite = FunctionTestSuite(suite_id="suite", requirement_id="r", name="module")
    db.add(suite)
    db.flush()
    db.add(FunctionTestCase(case_id="case", suite_id="suite", title="case"))
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "worker"))
    db.commit()
    await record_standalone_import(
        session,
        task=task,
        execution_id="run",
        attempt_id=attempt.id,
        actor_id="importer",
        changes=[ImportChange("function_suite", "suite", ("case",))],
    )
    db.commit()
    with pytest.raises(AppError):
        await delete_standalone_execution(session, task_id="task", execution_id="run")
    assert suite.effective_import_id is not None
    queue.status = "success"
    db.commit()
    attempt_id = attempt.id
    await delete_standalone_execution(session, task_id="task", execution_id="run")
    db.commit()
    db.expire_all()
    assert db.get(AiExecution, "run") is None
    assert db.get(AiGenerationAttempt, attempt_id) is None
    assert not db.scalars(select(AiGenerateVersionImport)).all()
    assert db.scalar(select(FunctionTestCase).where(FunctionTestCase.case_id == "case")) is not None
    assert (
        db.scalar(
            select(FunctionTestSuite).where(FunctionTestSuite.suite_id == "suite")
        ).effective_import_id
        is None
    )
    assert (
        db.scalar(select(AiGenerationStage).where(AiGenerationStage.task_id == "task")) is not None
    )


@pytest.mark.parametrize("kind", ["api", "ui"])
async def test_api_and_ui_provenance_preserve_target_scope(db, kind):  # noqa: F811
    from testing_agent.models.api_case import ApiCase
    from testing_agent.models.api_collection import ApiCollection
    from testing_agent.models.ui_test_case import UiTestCase
    from testing_agent.models.ui_test_suite import UiTestSuite

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    task.task_type = "api_case_generate" if kind == "api" else "ui_case_generate"
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
        checkpoint_enabled=True,
    )
    stage = db.get(AiGenerationStage, attempt.stage_id)
    stage.stage = "generate" if kind == "api" else "ui_yaml"
    execution.workflow_status, execution.current_stage = "success", "completed"
    attempt.status, attempt.output_content, attempt.output_format = "success", "valid", "yaml"
    attempt.review_status, attempt.reviewer_user_id = "approved", "reviewer"
    attempt.reviewed_at = datetime.now(UTC)
    if kind == "api":
        target = ApiCollection(collection_id="target", requirement_id="r", name="API")
        case = ApiCase(
            case_id="case", collection_id="target", name="case", method="GET", url_template="/x"
        )
        target_type = "api_collection"
    else:
        target = UiTestSuite(suite_id="target", requirement_id="r", name="UI")
        case = UiTestCase(case_id="case", suite_id="target", name="case", steps_json=[])
        target_type = "ui_suite"
    db.add(target)
    db.flush()
    db.add(case)
    db.commit()
    records = await record_standalone_import(
        session,
        task=task,
        execution_id="run",
        attempt_id=attempt.id,
        actor_id="importer",
        changes=[ImportChange(target_type, "target", ("case",))],
    )
    assert records[0].target_type == target_type and records[0].target_case_count == 1
    assert target.effective_import_id == records[0].import_id
    view = await project_standalone_execution(session, "run")
    assert view.imported_targets == [{"targetType": target_type, "targetId": "target"}]
