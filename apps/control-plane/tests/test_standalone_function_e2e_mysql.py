"""MySQL standalone functional launch through checkpoints, import and graph."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.direct_graph import cases_output, relations_output
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.core.errors import AppError
from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.worker_task import WorkerTaskRepository
from testing_agent.schemas.workers import (
    WorkerClaimRequest,
    WorkerProgressRequest,
    WorkerTaskEventRequest,
)
from testing_agent.services import ai_run_launcher, standalone_worker_authorization
from testing_agent.services.ai_candidate_review import GenerationCandidateReview
from testing_agent.services.ai_run_launcher import GenerationRunLauncher
from testing_agent.services.ai_stage_workflow import GenerationStageWorkflow
from testing_agent.services.ai_task_access import GenerationImportContext
from testing_agent.services.ai_task_commands import GenerationTaskCommands
from testing_agent.services.ai_task_queries import GenerationQueries
from testing_agent.services.ai_task_scope import GenerationAccess
from testing_agent.services.function_generate_import import import_function_run
from testing_agent.services.worker_task import WorkerTaskService


@pytest.mark.filterwarnings("error::sqlalchemy.exc.SAWarning")
async def test_function_checkpoint_workflow_and_import(mysql, monkeypatch):  # noqa: F811
    with mysql.begin() as connection:
        target = seed_row(connection, FunctionTestSuite.__table__, {"name": "任务管理"})
        project_id = connection.scalar(
            sa.select(Sprint.project_id)
            .join(Requirement, Requirement.sprint_id == Sprint.sprint_id)
            .where(Requirement.requirement_id == target["requirement_id"])
        )
        case = seed_row(
            connection,
            FunctionTestCase.__table__,
            {"suite_id": target["suite_id"], "title": "用例1"},
        )
        task = seed_row(
            connection,
            AiGenerateTask.__table__,
            {
                "task_type": "functional_case_generate",
                "sprint_id": "",
                "requirement_id": "",
                "project_id": project_id,
                "source_type": "text",
                "source_content": "原始业务要求",
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
            access.ensure_requirement_access = AsyncMock()
            access.validate_task_scope = AsyncMock()
            identifiers = iter(("function-run", "unused-1", "other-run", "unused-2"))
            launcher = GenerationRunLauncher(
                repository=repository,
                access=access,
                id_factory=lambda: next(identifiers),
            )
            body = {
                "connectionId": "llm",
                "checkpointEnabled": True,
                "requestId": "function-worker",
            }
            launched = await launcher.launch("function", task["task_id"], body, "actor")
            replayed = await launcher.launch("function", task["task_id"], body, "actor")
            assert launched["runId"] == replayed["runId"] == "function-run"
            assert not any("ai_generate_task_runs" in sql for sql in statements)
            # The final cutover revision drops the retired ledger, so the old
            # run cannot exist regardless of the new execution identity.
            with mysql.connect() as probe:
                assert "ai_generate_task_runs" not in sa.inspect(probe).get_table_names()
            statements.clear()
            worker = WorkerTaskService(WorkerTaskRepository(session))
            stages = GenerationStageWorkflow(repository=repository, owned_run=access.owned_run)
            stages.stage_connection = AsyncMock(return_value="llm")

            async def claim(expected):
                payload = await worker.claim("ai", WorkerClaimRequest(worker_id="agent"))
                if payload is None:
                    queued = await session.scalar(
                        sa.select(WorkerTask)
                        .where(WorkerTask.domain == "ai", WorkerTask.task_id == expected)
                        .execution_options(populate_existing=True)
                    )
                    assert payload is not None, (
                        f"Worker claim missed {expected}; "
                        f"queue status={getattr(queued, 'status', None)}, "
                        f"error={getattr(queued, 'error_message', None)}"
                    )
                assert payload["taskId"] == expected and payload["attemptId"] != "function-run"
                await worker.started("ai", expected, WorkerTaskEventRequest(worker_id="agent"))
                return payload

            first = await claim("function-worker")
            await worker.progress(
                "function-worker",
                WorkerProgressRequest(
                    worker_id="agent",
                    run_id=first["attemptId"],
                    current_stage="requirement_analysis",
                    stage_status="waiting_review",
                    config_json={"requirementAnalysis": {"scope": "initial"}},
                ),
            )
            # Keep the identity-mapped execution alive across the other session's
            # review so the next claim must refresh its current stage from MySQL.
            cached_execution = await session.get(AiExecution, "function-run")
            assert cached_execution.current_stage == "requirement_analysis"
            # Simulate a concurrent HTTP request whose repeatable-read snapshot
            # was established before the first review acquired and released its locks.
            async with sessions() as replay_session, sessions() as stale_review_session:
                replay_repository = AiGenerateTaskRepository(replay_session)
                replay_access = GenerationAccess(replay_repository)
                replay_access.owned_task = AsyncMock(
                    return_value=await replay_repository.get_task(task["task_id"])
                )
                await replay_session.scalar(
                    sa.select(AiExecution).where(AiExecution.execution_id == "function-run")
                )
                replay_stages = GenerationStageWorkflow(
                    repository=replay_repository, owned_run=replay_access.owned_run
                )
                replay_stages.stage_connection = AsyncMock(return_value="llm")
                stale_repository = AiGenerateTaskRepository(stale_review_session)
                stale_access = GenerationAccess(stale_repository)
                stale_access.owned_task = AsyncMock(
                    return_value=await stale_repository.get_task(task["task_id"])
                )
                stale_stages = GenerationStageWorkflow(
                    repository=stale_repository, owned_run=stale_access.owned_run
                )
                stale_stages.stage_connection = AsyncMock(return_value="llm")
                query_attempts = (
                    sa.select(sa.func.count())
                    .select_from(AiGenerationAttempt)
                    .where(AiGenerationAttempt.execution_id == "function-run")
                )
                assert await stale_review_session.scalar(query_attempts) == 1
                await stages.save_stage_output(
                    "function-run",
                    {
                        "stage": "requirement_analysis",
                        "configJson": {"requirementAnalysis": {"scope": "edited"}},
                    },
                    "actor",
                )
                assert await stale_review_session.scalar(query_attempts) == 1
                await stale_stages.review_stage(
                    "function-run",
                    {
                        "stage": "requirement_analysis",
                        "action": "approve",
                        "requestId": "case-worker",
                    },
                    "actor",
                )
                replay_review = await replay_stages.review_stage(
                    "function-run",
                    {
                        "stage": "requirement_analysis",
                        "action": "approve",
                        "requestId": "case-worker",
                    },
                    "actor",
                )
            assert (
                replay_review["runId"] == "function-run"
                and replay_review["currentStage"] == "case_names"
            )
            # Worker claim takes the queue lock first. A review replay holding
            # the execution lock must not wait on that queue and deadlock it.
            async with sessions() as busy_session, sessions() as review_session:
                await busy_session.scalar(
                    sa.select(WorkerTask)
                    .where(WorkerTask.domain == "ai", WorkerTask.task_id == "case-worker")
                    .with_for_update()
                )
                review_repository = AiGenerateTaskRepository(review_session)
                review_access = GenerationAccess(review_repository)
                review_access.owned_task = AsyncMock(
                    return_value=await review_repository.get_task(task["task_id"])
                )
                busy_review = GenerationStageWorkflow(
                    repository=review_repository, owned_run=review_access.owned_run
                )
                with pytest.raises(AppError):
                    await asyncio.wait_for(
                        busy_review.review_stage(
                            "function-run",
                            {
                                "stage": "requirement_analysis",
                                "action": "approve",
                                "requestId": "case-worker",
                            },
                            "actor",
                        ),
                        timeout=2,
                    )
                await review_session.rollback()
                await busy_session.rollback()
            # The worker poll is a separate request and starts a fresh transaction.
            await session.commit()
            current = await claim("case-worker")
            assert cached_execution.current_stage == "case_names"
            assert json.loads(current["configJson"])["requirementAnalysis"] == {"scope": "edited"}
            await worker.complete(
                "ai",
                "case-worker",
                WorkerTaskEventRequest(
                    worker_id="agent",
                    run_id=current["attemptId"],
                    status="failed",
                    error_message="model failed",
                ),
            )
            failed = await GenerationQueries(repository, access).get_run(
                "function", "function-run", "actor"
            )
            assert failed["errorMessage"] == "model failed"
            await stages.retry_stage(
                "function-run", {"stage": "case_names", "requestId": "retry-worker"}, "actor"
            )
            current = await claim("retry-worker")
            async with sessions() as prior_snapshot:
                stale_repository = AiGenerateTaskRepository(prior_snapshot)
                stale_access = GenerationAccess(stale_repository)
                stale_access.owned_task = AsyncMock(
                    return_value=await stale_repository.get_task(task["task_id"])
                )
                stale_stages = GenerationStageWorkflow(
                    repository=stale_repository, owned_run=stale_access.owned_run
                )
                stale_stages.stage_connection = AsyncMock(return_value="llm")
                await worker.progress(
                    "retry-worker",
                    WorkerProgressRequest(
                        worker_id="agent",
                        run_id=current["attemptId"],
                        current_stage="case_names",
                        stage_status="waiting_review",
                        config_json={
                            "requirementAnalysis": {"scope": "edited"},
                            "caseNames": {"points": ["login"]},
                        },
                    ),
                )
                await stale_stages.review_stage(
                    "function-run",
                    {"stage": "case_names", "action": "approve", "requestId": "final-worker"},
                    "actor",
                )
            current = await claim("final-worker")
            await worker.complete(
                "ai",
                "final-worker",
                WorkerTaskEventRequest(
                    worker_id="agent",
                    run_id=current["attemptId"],
                    status="success",
                    result_yaml=cases_output(),
                    config_json={
                        "requirementAnalysis": {"scope": "edited"},
                        "caseNames": {"points": ["login"]},
                    },
                ),
            )
            reviewer = GenerationCandidateReview(repository, access.owned_run)
            approved = await reviewer.review(
                "function", "function-run", {"action": "approve"}, "actor"
            )
            assert approved["reviewStatus"] == "approved"
            context = GenerationImportContext(repository, access)
            preview = await import_function_run(
                context,
                "function-run",
                False,
                "actor",
                target_requirement_id=target["requirement_id"],
            )
            assert preview["requiresConfirmation"]
            imported = await import_function_run(
                context,
                "function-run",
                True,
                "actor",
                target_requirement_id=target["requirement_id"],
            )
            assert imported["run"]["importStatus"] == "imported"
            graph = await stages.generate_relation_analysis(
                "function-run", {"requestId": "graph-worker"}, "actor"
            )
            assert graph["currentStage"] == "relation_analysis"
            current = await claim("graph-worker")
            await worker.complete(
                "ai",
                "graph-worker",
                WorkerTaskEventRequest(
                    worker_id="agent",
                    run_id=current["attemptId"],
                    status="success",
                    config_json={
                        "requirementAnalysis": {"scope": "edited"},
                        "caseNames": {"points": ["login"]},
                        "caseRelations": relations_output(),
                    },
                ),
            )
            history = await GenerationQueries(repository, access).list_run_summaries(
                "function", task["task_id"], "actor"
            )
            assert history["total"] == 1 and history["items"][0]["importStatus"] == "imported"
            commands = GenerationTaskCommands(repository, access)
            await commands.delete_run("function", "function-run", "actor")
            preserved = await session.scalar(
                sa.select(FunctionTestCase).where(FunctionTestCase.case_id == case["case_id"])
            )
            suite = await session.scalar(
                sa.select(FunctionTestSuite).where(FunctionTestSuite.suite_id == target["suite_id"])
            )
            assert preserved and suite.effective_import_id is None
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
                    WorkerTask.task_id.in_(
                        [
                            "function-worker",
                            "case-worker",
                            "retry-worker",
                            "final-worker",
                            "graph-worker",
                        ]
                    )
                )
            )
            connection.execute(sa.delete(AiGenerateTask))
