"""Independent functional relation analysis preserves one execution and its history."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db
from support.direct_graph import cases_output

from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.standalone_execution import lock_or_create_stage
from testing_agent.services.ai_stage_workflow import GenerationStageWorkflow
from testing_agent.services.standalone_execution import start_standalone_execution
from testing_agent.services.standalone_execution_view import project_standalone_execution


async def test_relation_analysis_keeps_execution_identity(db):  # noqa: F811
    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    execution, initial, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="run",
        request_id="initial",
        actor_id="user",
        connection_id="llm",
        source={"sourceContent": "sample"},
        config={},
        checkpoint_enabled=True,
    )
    initial.status = "success"
    initial.output_content = "{}"
    initial.output_format = "json"
    execution.workflow_status = "success"
    execution.current_stage = "completed"
    stage, _ = await lock_or_create_stage(session, task.task_id, "detailed_cases")
    session.add(
        AiGenerationAttempt(
            id="final-attempt",
            stage_id=stage.id,
            execution_id="run",
            attempt_no=1,
            operation="generate",
            requested_by="user",
            input_snapshot_json={},
            output_content=cases_output(),
            output_format="yaml",
            status="success",
            review_status="approved",
            reviewer_user_id="user",
            reviewed_at=datetime.now(UTC),
            invalidated_reason="",
        )
    )
    await session.flush()

    async def owned_run(user_id, run_id, kind=None, *, action="read"):
        return await project_standalone_execution(session, run_id)

    stages = GenerationStageWorkflow(
        repository=AiGenerateTaskRepository(session), owned_run=owned_run
    )
    stages.stage_connection = AsyncMock(return_value="llm")

    first = await stages.generate_relation_analysis("run", {"requestId": "graph"}, "user")
    replay = await stages.generate_relation_analysis("run", {"requestId": "graph"}, "user")

    assert first["runId"] == replay["runId"] == "run"
    assert first["currentStage"] == replay["currentStage"] == "relation_analysis"
    queues = db.scalars(select(WorkerTask).where(WorkerTask.task_id == "graph")).all()
    assert len(queues) == 1
    assert execution.execution_id == "run"
    attempts = db.scalars(
        select(AiGenerationAttempt).where(AiGenerationAttempt.execution_id == "run")
    ).all()
    assert all(attempt.execution_id == "run" for attempt in attempts)
