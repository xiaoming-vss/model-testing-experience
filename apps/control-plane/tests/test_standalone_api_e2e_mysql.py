"""Real-MySQL standalone API launch, callbacks, review, import and deletion."""

from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_collection import ApiCollection
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
from testing_agent.services.ai_task_commands import GenerationTaskCommands
from testing_agent.services.ai_task_queries import GenerationQueries
from testing_agent.services.ai_task_scope import GenerationAccess
from testing_agent.services.api_generate_import import ApiCandidateImporter
from testing_agent.services.worker_task import WorkerTaskService


@pytest.mark.parametrize("two_stage", [False, True])
async def test_standalone_api_end_to_end(mysql, monkeypatch, two_stage):  # noqa: F811
    with mysql.begin() as connection:
        target = seed_row(connection, ApiCollection.__table__)
        project_id = connection.scalar(
            sa.select(Sprint.project_id)
            .join(Requirement, Requirement.sprint_id == Sprint.sprint_id)
            .where(Requirement.requirement_id == target["requirement_id"])
        )
        case = seed_row(
            connection,
            ApiCase.__table__,
            {
                "collection_id": target["collection_id"],
                "name": "Login",
                "method": "GET",
                "url_template": "/old",
            },
        )
        task = seed_row(
            connection,
            AiGenerateTask.__table__,
            {
                "task_type": "api_case_generate",
                "sprint_id": "",
                "requirement_id": "",
                "project_id": project_id,
                "source_type": "text",
                "source_content": "OpenAPI input",
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
                source_archive_repository=None,
                access=access,
                id_factory=lambda: next(ids),
            )
            body = {"connectionId": "llm"}
            if two_stage:
                body["apiWorkflowVersion"] = "api_two_stage/1.0"
            launched = await launcher.launch("api", task["task_id"], body, "actor")
            assert launched["runId"] == "api-e2e-run" and launched["status"] == "pending"
            assert not any("ai_generate_task_runs" in sql for sql in statements)
            # The final cutover revision drops the retired ledger, so the old
            # run cannot exist regardless of the new execution identity.
            with mysql.connect() as probe:
                assert "ai_generate_task_runs" not in sa.inspect(probe).get_table_names()
            statements.clear()
            queue = await session.scalar(
                sa.select(WorkerTask).where(WorkerTask.task_id == "api-e2e-worker")
            )
            assert queue.run_id != launched["runId"]
            commands = GenerationTaskCommands(repository, None, access)
            with pytest.raises(AppError):
                await commands.delete("api", task["task_id"], "actor")
            await session.rollback()
            worker = WorkerTaskService(WorkerTaskRepository(session))
            claim = await worker.claim("ai", WorkerClaimRequest(worker_id="agent"))
            assert claim["taskId"] == "api-e2e-worker" and claim["attemptId"] != launched["runId"]
            await worker.started("ai", "api-e2e-worker", WorkerTaskEventRequest(worker_id="agent"))
            if two_stage:
                extraction = {"login": {"method": "GET", "path": "/login"}}
                await worker.progress(
                    "api-e2e-worker",
                    WorkerProgressRequest(
                        worker_id="agent",
                        run_id=claim["attemptId"],
                        current_stage="openapi_extract",
                        stage_status="waiting_review",
                        config_json={"apiExtraction": extraction},
                    ),
                )
                stages = GenerationStageWorkflow(repository=repository, owned_run=access.owned_run)
                stages.stage_connection = AsyncMock(return_value="llm")
                extraction = {"login": {"method": "POST", "path": "/edited"}}
                await stages.save_api_checkpoint(
                    "api-e2e-run",
                    {"stage": "openapi_extract", "configJson": {"apiExtraction": extraction}},
                    "actor",
                )
                revision = {
                    "stage": "openapi_extract",
                    "revisionInstruction": "补充边界",
                    "requestId": "api-revision",
                }
                await stages.revise_api_stage("api-e2e-run", revision, "actor")
                assert (await stages.revise_api_stage("api-e2e-run", revision, "actor"))[
                    "runId"
                ] == "api-e2e-run"
                claim = await worker.claim("ai", WorkerClaimRequest(worker_id="agent"))
                assert claim["taskId"] == "api-revision" and "/edited" in claim["configJson"]
                await worker.started(
                    "ai", "api-revision", WorkerTaskEventRequest(worker_id="agent")
                )
                await worker.progress(
                    "api-revision",
                    WorkerProgressRequest(
                        worker_id="agent",
                        run_id=claim["attemptId"],
                        current_stage="openapi_extract",
                        stage_status="waiting_review",
                        config_json={"apiExtraction": extraction},
                    ),
                )
                request = {
                    "stage": "openapi_extract",
                    "action": "approve",
                    "requestId": "api-next-worker",
                }
                continued = await stages.review_api_checkpoint("api-e2e-run", request, "actor")
                assert continued["currentStage"] == "generate"
                assert (await stages.review_api_checkpoint("api-e2e-run", request, "actor"))[
                    "runId"
                ] == "api-e2e-run"
                claim = await worker.claim("ai", WorkerClaimRequest(worker_id="agent"))
                assert claim["taskId"] == "api-next-worker"
                await worker.started(
                    "ai", "api-next-worker", WorkerTaskEventRequest(worker_id="agent")
                )
            worker_id = "api-next-worker" if two_stage else "api-e2e-worker"
            await worker.progress(
                worker_id,
                WorkerProgressRequest(
                    worker_id="agent",
                    run_id=claim["attemptId"],
                    current_stage="generate" if two_stage else "openapi_extract",
                    stage_status="running",
                    config_json={},
                ),
            )
            await worker.complete(
                "ai",
                worker_id,
                WorkerTaskEventRequest(
                    worker_id="agent",
                    run_id=claim["attemptId"],
                    status="success",
                    result_yaml="cases:\n  - name: Login\n    method: GET\n    urlTemplate: /new\n",
                    config_json={"apiExtraction": extraction} if two_stage else {},
                ),
            )
            review = GenerationCandidateReview(repository, access.owned_run)
            reviewed = await review.review("api", "api-e2e-run", {"action": "approve"}, "actor")
            assert reviewed["reviewStatus"] == "approved"
            importer = ApiCandidateImporter(
                repository=repository,
                owned_run=access.owned_run,
                ensure_collection_access=AsyncMock(),
            )
            preview = await importer.import_api_run(
                "api-e2e-run", target["collection_id"], False, "actor"
            )
            assert preview["requiresConfirmation"]
            result = await importer.import_api_run(
                "api-e2e-run", target["collection_id"], True, "actor"
            )
            assert result["run"]["importStatus"] == "imported"
            history = await GenerationQueries(repository, None, access).list_run_summaries(
                "api", task["task_id"], "actor"
            )
            assert history["total"] == 1 and history["items"][0]["importStatus"] == "imported"
            assert await commands.delete_run("api", "api-e2e-run", "actor") == {}
            row = await session.scalar(sa.select(ApiCase).where(ApiCase.case_id == case["case_id"]))
            collection = await session.scalar(
                sa.select(ApiCollection).where(
                    ApiCollection.collection_id == target["collection_id"]
                )
            )
            assert row.url_template == "/new" and collection.effective_import_id is None
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
            assert (
                await session.scalar(
                    sa.select(AiGenerateVersionImport.id).where(
                        AiGenerateVersionImport.target_id == target["collection_id"]
                    )
                )
                is None
            )
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(
                sa.delete(WorkerTask).where(
                    WorkerTask.task_id.in_(["api-e2e-worker", "api-next-worker", "api-revision"])
                )
            )
            connection.execute(sa.delete(AiGenerateTask))
