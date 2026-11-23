"""Real-MySQL standalone functional relation-analysis dispatch."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.direct_graph import cases_output, relations_output
from support.mysql_initialization import mysql, seed_row  # noqa: F401
from support.requirement_versions import material_artifact

from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.project import Project
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.standalone_execution import lock_or_create_stage
from testing_agent.repositories.worker_task import WorkerTaskRepository
from testing_agent.schemas.workers import (
    WorkerClaimRequest,
    WorkerTaskEventRequest,
)
from testing_agent.services import ai_run_launcher, standalone_worker_authorization
from testing_agent.services.ai_run_launcher import GenerationRunLauncher
from testing_agent.services.ai_stage_workflow import GenerationStageWorkflow
from testing_agent.services.ai_task_queries import GenerationQueries
from testing_agent.services.ai_task_scope import GenerationAccess
from testing_agent.services.standalone_execution_view import project_standalone_execution
from testing_agent.services.worker_task import WorkerTaskService


@pytest.mark.filterwarnings("error::sqlalchemy.exc.SAWarning")
async def test_function_relation_analysis_dispatch(mysql, monkeypatch):  # noqa: F811
    with mysql.begin() as connection:
        project = seed_row(connection, Project.__table__)
        task = seed_row(
            connection,
            AiGenerateTask.__table__,
            {
                "task_type": "functional_case_generate",
                "sprint_id": "",
                "requirement_id": "",
                "project_id": project["project_id"],
                "source_type": "text",
                "source_content": json.dumps(material_artifact(), ensure_ascii=False),
            },
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    statements = []
    sa.event.listen(
        engine.sync_engine,
        "before_cursor_execute",
        lambda _c, _u, sql, _p, _x, _m: statements.append(sql.lower()),
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(ai_run_launcher, "require_project_access", AsyncMock())
    monkeypatch.setattr(ai_run_launcher, "require_personal_connection", AsyncMock())
    monkeypatch.setattr(
        standalone_worker_authorization, "authorize_worker_actor", AsyncMock(return_value="actor")
    )
    try:
        async with sessions() as session:
            repository = AiGenerateTaskRepository(session)
            row = await repository.get_task(task["task_id"])
            access = GenerationAccess(repository)
            access.owned_task = AsyncMock(return_value=row)
            access.ensure_project_access = AsyncMock()
            access.ensure_sprint_access = AsyncMock()
            access.validate_task_scope = AsyncMock()
            ids = iter(("function-run", "function-worker"))
            launcher = GenerationRunLauncher(
                repository=repository,
                access=access,
                id_factory=lambda: next(ids),
            )
            launched = await launcher.launch(
                "function", task["task_id"], {"connectionId": "llm"}, "actor"
            )
            assert launched["runId"] == "function-run"
            execution = await session.get(AiExecution, "function-run")
            initial = await session.scalar(
                sa.select(AiGenerationAttempt).where(
                    AiGenerationAttempt.execution_id == "function-run"
                )
            )
            initial.status = "success"
            initial.output_content = "{}"
            initial.output_format = "json"
            execution.workflow_status = "success"
            execution.current_stage = "completed"
            initial_queue = await session.scalar(
                sa.select(WorkerTask).where(WorkerTask.task_id == "function-worker")
            )
            initial_queue.status = "success"
            initial_queue.finished_at = datetime.now(UTC)
            stage, _ = await lock_or_create_stage(session, task["task_id"], "detailed_cases")
            session.add(
                AiGenerationAttempt(
                    id="final-attempt",
                    stage_id=stage.id,
                    execution_id="function-run",
                    attempt_no=1,
                    operation="generate",
                    requested_by="actor",
                    input_snapshot_json={},
                    output_content=cases_output(),
                    output_format="yaml",
                    status="success",
                    review_status="approved",
                    reviewer_user_id="reviewer",
                    reviewed_at=datetime.now(UTC),
                    invalidated_reason="",
                )
            )
            await session.commit()

            stages = GenerationStageWorkflow(repository=repository, owned_run=access.owned_run)
            stages.stage_connection = AsyncMock(return_value="llm")
            graph = await stages.generate_relation_analysis(
                "function-run", {"requestId": "graph-worker"}, "actor"
            )
            assert graph["currentStage"] == "relation_analysis"
            # The graph command committed; the worker claim needs a fresh
            # transaction to set its own isolation level.
            await session.rollback()

            worker = WorkerTaskService(WorkerTaskRepository(session))
            claim = await worker.claim("ai", WorkerClaimRequest(worker_id="agent"))
            assert claim["taskId"] == "graph-worker"
            await worker.started("ai", "graph-worker", WorkerTaskEventRequest(worker_id="agent"))
            await worker.complete(
                "ai",
                "graph-worker",
                WorkerTaskEventRequest(
                    worker_id="agent",
                    run_id=claim["attemptId"],
                    status="success",
                    config_json={
                        "requirementAnalysis": {},
                        "caseRelations": relations_output(),
                    },
                ),
            )
            projected = await project_standalone_execution(session, "function-run")
            assert projected.config_json["caseRelations"] == relations_output()
            history = await GenerationQueries(repository, access).list_run_summaries(
                "function", task["task_id"], "actor"
            )
            assert history["total"] == 1
            retired_sql = [
                sql
                for sql in statements
                if any(
                    table in sql
                    for table in (
                        "ai_generate_task_runs",
                        "ai_generate_run_stages",
                        "ai_generate_stage_attempts",
                        "ai_generate_run_imports",
                    )
                )
            ]
            assert not retired_sql, retired_sql
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(
                sa.delete(WorkerTask).where(
                    WorkerTask.task_id.in_(["function-worker", "graph-worker"])
                )
            )
            connection.execute(sa.delete(AiGenerateTask))
