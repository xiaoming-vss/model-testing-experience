"""Real-MySQL standalone API launch, worker callbacks, history and deletion."""

from unittest.mock import AsyncMock

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql, seed_api_interface, seed_row  # noqa: F401

from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.project import Project
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.worker_task import WorkerTaskRepository
from testing_agent.schemas.workers import (
    WorkerClaimRequest,
    WorkerProgressRequest,
    WorkerTaskEventRequest,
)
from testing_agent.services import ai_run_launcher, standalone_worker_authorization
from testing_agent.services.ai_run_launcher import GenerationRunLauncher
from testing_agent.services.ai_task_commands import GenerationTaskCommands
from testing_agent.services.ai_task_queries import GenerationQueries
from testing_agent.services.ai_task_scope import GenerationAccess
from testing_agent.services.worker_task import WorkerTaskService


async def test_standalone_api_launch_and_worker_callbacks(mysql, monkeypatch):  # noqa: F811
    with mysql.begin() as connection:
        project = seed_row(connection, Project.__table__)
        interface = seed_api_interface(connection, project["project_id"])
        task = seed_row(
            connection,
            AiGenerateTask.__table__,
            {
                "task_type": "api_case_generate",
                "sprint_id": "",
                "requirement_id": "",
                "project_id": project["project_id"],
                "source_type": "interface_library",
                "source_content": "",
                "interface_ids_json": [interface["interface_id"]],
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
            ids = iter(("api-e2e-run", "api-e2e-worker"))
            launcher = GenerationRunLauncher(
                repository=repository,
                access=access,
                id_factory=lambda: next(ids),
            )
            launched = await launcher.launch(
                "api", task["task_id"], {"connectionId": "llm"}, "actor"
            )
            assert launched["runId"] == "api-e2e-run" and launched["status"] == "pending"
            assert not any("ai_generate_task_runs" in sql for sql in statements)
            with mysql.connect() as probe:
                assert "ai_generate_task_runs" not in sa.inspect(probe).get_table_names()
            statements.clear()
            # The launcher committed; end this session's snapshot before the
            # worker claim starts its own READ COMMITTED transaction.
            await session.rollback()

            worker = WorkerTaskService(WorkerTaskRepository(session))
            claim = await worker.claim("ai", WorkerClaimRequest(worker_id="agent"))
            assert claim["taskId"] == "api-e2e-worker"
            await worker.started("ai", "api-e2e-worker", WorkerTaskEventRequest(worker_id="agent"))
            await worker.progress(
                "api-e2e-worker",
                WorkerProgressRequest(
                    worker_id="agent",
                    run_id=claim["attemptId"],
                    current_stage="generate",
                    stage_status="running",
                    config_json={},
                ),
            )
            await worker.complete(
                "ai",
                "api-e2e-worker",
                WorkerTaskEventRequest(
                    worker_id="agent",
                    run_id=claim["attemptId"],
                    status="success",
                    result_yaml="cases:\n  - name: Login\n    method: GET\n    urlTemplate: /new\n",
                    config_json={},
                ),
            )
            history = await GenerationQueries(repository, access).list_run_summaries(
                "api", task["task_id"], "actor"
            )
            assert history["total"] == 1
            commands = GenerationTaskCommands(repository, access)
            assert await commands.delete_run("api", "api-e2e-run", "actor") == {}
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
                        "ai_generate_stage_versions",
                        "ai_generate_version_imports",
                    )
                )
            ]
            assert not retired_sql, retired_sql
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(
                sa.delete(WorkerTask).where(WorkerTask.task_id.in_(["api-e2e-worker"]))
            )
            connection.execute(sa.delete(AiGenerateTask))
