"""Real MySQL exercise of the independent Worker callback transaction."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.direct_graph import cases_output
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.worker_task import WorkerTaskRepository
from testing_agent.schemas.workers import (
    WorkerClaimRequest,
    WorkerProgressRequest,
    WorkerTaskEventRequest,
)
from testing_agent.services import standalone_worker_authorization as auth
from testing_agent.services.standalone_execution import start_standalone_execution
from testing_agent.services.standalone_execution_view import project_standalone_execution
from testing_agent.services.worker_task import WorkerTaskService


async def test_worker_callbacks_persist_execution_and_attempts_in_mysql(mysql, monkeypatch):  # noqa: F811
    with mysql.begin() as connection:
        task_row = seed_row(
            connection,
            AiGenerateTask.__table__,
            {"task_type": "functional_case_generate", "sprint_id": "", "requirement_id": ""},
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(auth, "authorize_worker_actor", AsyncMock(return_value="user"))
    try:
        async with sessions() as session:
            task = await session.scalar(
                sa.select(AiGenerateTask)
                .where(AiGenerateTask.task_id == task_row["task_id"])
                .with_for_update()
            )
            execution, first, _ = await start_standalone_execution(
                session,
                task=task,
                execution_id="mysql-run",
                request_id="mysql-worker",
                actor_id="user",
                connection_id="llm",
                source={},
                config={},
                checkpoint_enabled=False,
            )
            execution_id, attempt_id = execution.execution_id, first.id
            await session.commit()
        async with sessions() as session:
            service = WorkerTaskService(WorkerTaskRepository(session))
            claim = await service.claim("ai", WorkerClaimRequest(worker_id="agent"))
            assert claim["attemptId"] == attempt_id
            await service.started("ai", "mysql-worker", WorkerTaskEventRequest(worker_id="agent"))
            await service.progress(
                "mysql-worker",
                WorkerProgressRequest(
                    worker_id="agent",
                    run_id=attempt_id,
                    current_stage="case_names",
                    stage_status="running",
                    config_json={
                        "requirementAnalysis": {"purpose": "login"},
                        "caseNames": {"points": ["login"]},
                    },
                ),
            )
            await service.complete(
                "ai",
                "mysql-worker",
                WorkerTaskEventRequest(
                    worker_id="agent",
                    run_id=attempt_id,
                    status="success",
                    result_yaml=cases_output(),
                    config_json={
                        "requirementAnalysis": {"purpose": "login"},
                        "caseNames": {"points": ["login"]},
                    },
                ),
            )
        async with sessions() as session:
            run = await project_standalone_execution(session, execution_id)
            attempts = (
                await session.scalars(
                    sa.select(AiGenerationAttempt).where(
                        AiGenerationAttempt.execution_id == execution_id
                    )
                )
            ).all()
            assert run.status == "success" and run.result_yaml == cases_output()
            assert len(attempts) == 3 and all(item.status == "success" for item in attempts)
            from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
            from testing_agent.services.ai_task_queries import GenerationQueries

            access = SimpleNamespace(owned_task=AsyncMock())
            queries = GenerationQueries(AiGenerateTaskRepository(session), access)
            detail = await queries.get_run("function", execution_id, "reader")
            assert detail["runId"] == execution_id and detail["resultYaml"] == cases_output()
            access.owned_task.assert_awaited_once_with(
                "reader", task_row["task_id"], "function", action="read"
            )
            from testing_agent.handlers.generation_guards import (
                ensure_legacy_mutation_allowed,
            )
            from testing_agent.services.ai_candidate_review import GenerationCandidateReview
            from testing_agent.services.ai_task_scope import GenerationAccess

            repository = AiGenerateTaskRepository(session)
            generation_access = GenerationAccess(repository)
            owned_task = await repository.get_task(task_row["task_id"])
            generation_access.owned_task = AsyncMock(return_value=owned_task)
            review = GenerationCandidateReview(repository, generation_access.owned_run)
            await ensure_legacy_mutation_allowed(
                generation_access.owned_run, "function", execution_id, "reviewer", action="write"
            )
            edited = await review.update_result(
                "function", execution_id, cases_output(), "reviewer"
            )
            assert edited["reviewStatus"] == "pending"
            approved = await review.review(
                "function", execution_id, {"action": "approve", "comment": "ready"}, "reviewer"
            )
            assert (
                approved["reviewStatus"] == "approved" and approved["reviewerUserId"] == "reviewer"
            )
            history = await GenerationQueries(repository, generation_access).list_run_summaries(
                "function",
                task_row["task_id"],
                "reviewer",
                page=1,
                page_size=20,
                pipeline_filter="import_pending",
            )
            assert history["total"] == 1 and history["items"][0]["runId"] == execution_id
            assert history["items"][0]["reviewStatus"] == "approved"
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(sa.delete(WorkerTask).where(WorkerTask.task_id == "mysql-worker"))
            connection.execute(
                sa.delete(AiGenerateTask).where(AiGenerateTask.task_id == task_row["task_id"])
            )
