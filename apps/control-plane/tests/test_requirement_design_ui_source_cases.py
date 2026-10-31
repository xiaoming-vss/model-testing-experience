"""The requirement entry must preserve the user's selection through the real launch path."""

from uuid import uuid4

from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db
from support.generation import generation_services
from support.ui_generation_flow import read, setup

from testing_agent.models.ai_generate_task import AiGenerateTaskRun
from testing_agent.models.ai_generate_task_source_archive import AiGenerateTaskSourceArchive
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.schemas.requirement_design import RequirementDesignRunRequest


async def test_requirement_ui_selection_reaches_frozen_run_inputs(db):
    previous, worker, _, _ = setup(db)
    previous.status = "failed"
    worker.status = "failed"
    from datetime import UTC, datetime

    db.add(
        AiGenerateTaskSourceArchive(
            archive_id="source",
            task_id="ui-task",
            filename="source.zip",
            file_id="source-file",
            size_bytes=10,
            sha256="0" * 64,
            uploaded_at=datetime.now(UTC),
        )
    )
    db.add(FunctionTestSuite(suite_id="formal", requirement_id="r", name="正式用例"))
    db.flush()
    for index in (1, 2):
        db.add(
            FunctionTestCase(
                case_id=f"formal-{index}",
                suite_id="formal",
                title=f"用例{index}",
                content_json=read("cases")[0]["content"],
            )
        )
    db.commit()
    service = generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(db))).design
    request = RequirementDesignRunRequest(
        taskId="ui-task",
        requestId=uuid4(),
        connectionId="llm",
        functionCaseIds=["formal-2"],
        checkpointEnabled=False,
    )
    result = await service.start("r", "ui", request, "u")
    saved = db.query(AiGenerateTaskRun).filter_by(run_id=result["runId"]).one()
    assert saved.current_stage == "ui_surface" and saved.checkpoint_enabled is True
    assert [case["caseId"] for case in saved.snapshot_json["functionalCases"]] == ["formal-2"]
    assert saved.snapshot_json["functionalCases"][0]["title"] == "用例2"
