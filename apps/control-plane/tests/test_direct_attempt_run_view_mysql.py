"""Existing direct-stage run IDs resolve without the old ledger on MySQL."""

from unittest.mock import AsyncMock

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.requirement_design import RequirementDesignRepository
from testing_agent.schemas.ai_generate_task import AiGenerateTaskRunResponse
from testing_agent.services.ai_task_queries import GenerationQueries
from testing_agent.services.ai_task_scope import GenerationAccess


async def test_direct_detail_resolves_stage_attempt_without_old_run_table(mysql):  # noqa: F811
    with mysql.begin() as connection:
        requirement = seed_row(connection, Requirement.__table__)
        sprint = (
            connection.execute(
                sa.select(Sprint).where(Sprint.sprint_id == requirement["sprint_id"])
            )
            .mappings()
            .one()
        )
        task = seed_row(
            connection,
            AiGenerateTask.__table__,
            {
                "task_type": "api_case_generate",
                "project_id": sprint["project_id"],
                "sprint_id": sprint["sprint_id"],
                "requirement_id": requirement["requirement_id"],
            },
        )
        stage = seed_row(
            connection,
            AiGenerationStage.__table__,
            {"task_id": task["task_id"], "stage": "openapi_extract"},
        )
        attempt = seed_row(
            connection,
            AiGenerationAttempt.__table__,
            {
                "stage_id": stage["id"],
                "status": "success",
                "worker_task_id": "context-worker",
                "output_content": '{"path":"/login"}',
                "output_format": "json",
                "input_snapshot_json": {
                    "source": {"sourceContent": "frozen"},
                    "llmConnectionId": "personal-model",
                },
            },
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    statements = []
    sa.event.listen(
        engine.sync_engine,
        "before_cursor_execute",
        lambda _c, _u, sql, _p, _x, _m: statements.append(sql.lower()),
    )
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            repository = AiGenerateTaskRepository(session)
            access = GenerationAccess(repository)
            access.owned_task = AsyncMock(return_value=await repository.get_task(task["task_id"]))
            queries = GenerationQueries(repository, access)
            result = await queries.get_run("api", attempt["id"], "user")
            AiGenerateTaskRunResponse.model_validate(result)
            assert result["runId"] == attempt["id"] and result["generationChainManaged"]
            assert result["configJson"]["apiExtraction"] == {"path": "/login"}
            history = await queries.list_run_summaries("api", task["task_id"], "user")
            assert history["total"] == 1 and history["items"][0]["runId"] == attempt["id"]
            assert history["items"][0]["availableArtifacts"] == ["apiExtraction"]
            from testing_agent.models.worker_task import WorkerTask
            from testing_agent.repositories.worker_context import read_worker_context

            context_task = WorkerTask(
                domain="ai",
                task_id="context-worker",
                task_type="api_case_generate",
                run_id=attempt["id"],
                status="running",
            )
            context = await session.run_sync(lambda sync: read_worker_context(sync, context_task))
            assert context.generate_task_id == task["task_id"]
            assert context.llm_connection_id == "personal-model"
            context_task.task_id = "other-worker"
            context = await session.run_sync(lambda sync: read_worker_context(sync, context_task))
            assert context.generate_task_id is None and context.llm_connection_id is None
            design = RequirementDesignRepository(session)
            assert (await design.run_counts(requirement["requirement_id"]))["api"] == 1
            assert await design.active_task_ids(requirement["requirement_id"]) == []
            design_history = await design.history(
                requirement["requirement_id"], "api", 1, 20, "all"
            )
            assert design_history["total"] == 1
            assert design_history["items"][0]["runId"] == attempt["id"]
            active = await session.get(AiGenerationAttempt, attempt["id"])
            active.status = "running"
            await session.flush()
            assert await design.active_task_ids(requirement["requirement_id"]) == [task["task_id"]]
            assert not any("ai_generate_task_runs" in statement for statement in statements)
            assert access.owned_task.await_count == 2
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            # The generic seeder creates extra parent stages for foreign-key defaults.
            connection.execute(sa.delete(AiGenerationStage))
            connection.execute(
                sa.delete(AiGenerateTask).where(AiGenerateTask.task_id == task["task_id"])
            )


async def test_direct_worker_uses_dispatch_actor_personal_model_connection(mysql, monkeypatch):  # noqa: F811
    from types import SimpleNamespace

    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.repositories.worker_task import WorkerTaskRepository
    from testing_agent.services.stage_storage.worker_service import DirectStageWorkerService
    from testing_agent.services.worker_task import WorkerTaskService

    with mysql.begin() as connection:
        task = seed_row(connection, AiGenerateTask.__table__, {"task_type": "test_report_generate"})
        stage = seed_row(
            connection,
            AiGenerationStage.__table__,
            {"task_id": task["task_id"], "stage": "generate"},
        )
        attempt = seed_row(
            connection,
            AiGenerationAttempt.__table__,
            {"stage_id": stage["id"], "status": "claimed", "worker_task_id": "worker"},
        )
        seed_row(
            connection,
            WorkerTask.__table__,
            {
                "domain": "ai",
                "task_id": "worker",
                "run_id": attempt["id"],
                "task_type": "test_report_generate",
                "status": "claimed",
            },
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    authorization = SimpleNamespace(
        actor_id="actor",
        task=SimpleNamespace(project_id=task["project_id"]),
        input_snapshot={"llmConnectionId": "connection"},
    )
    monkeypatch.setattr(
        DirectStageWorkerService, "authorize", AsyncMock(return_value=authorization)
    )
    connection = SimpleNamespace(
        secret_json={"apiKey": "test-secret"},
        extra_json={"modelId": "model"},
        access_token="",
        connection_id="connection",
        base_url="https://example.invalid",
    )
    personal = AsyncMock(return_value=connection)
    monkeypatch.setattr("testing_agent.services.worker_task.require_personal_connection", personal)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            payload = await WorkerTaskService(WorkerTaskRepository(session)).llm_credentials(
                "worker"
            )
            assert payload["apiKey"] == "test-secret"
            personal.assert_awaited_once_with(
                session, "actor", "llm", "connection", task["project_id"]
            )
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(sa.delete(WorkerTask).where(WorkerTask.task_id == "worker"))
            connection.execute(sa.delete(AiGenerationStage))
            connection.execute(
                sa.delete(AiGenerateTask).where(AiGenerateTask.task_id == task["task_id"])
            )
