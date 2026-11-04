"""Independent API checkpoint continuation shares execution and preserves inputs."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db

from testing_agent.core.errors import AppError, ErrForbidden
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.schemas.workers import (
    WorkerClaimRequest,
    WorkerProgressRequest,
    WorkerTaskEventRequest,
)
from testing_agent.services import standalone_worker_authorization as auth
from testing_agent.services.ai_stage_workflow import GenerationStageWorkflow
from testing_agent.services.standalone_api_stage import (
    retry_api_stage,
    review_api_checkpoint,
    revise_api_stage,
    save_api_checkpoint,
)
from testing_agent.services.standalone_execution import start_standalone_execution
from testing_agent.services.standalone_execution_view import project_standalone_execution
from testing_agent.services.standalone_worker_service import StandaloneWorkerService


async def test_api_checkpoint_continues_and_retries(db, monkeypatch):  # noqa: F811
    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    task.task_type = "api_case_generate"
    db.commit()
    session = AsyncSessionAdapter(db)
    await start_standalone_execution(
        session,
        task=task,
        execution_id="run",
        request_id="first",
        actor_id="user",
        connection_id="llm",
        source={"apiWorkflowVersion": "api_two_stage/1.0"},
        config={},
        checkpoint_enabled=True,
    )
    db.commit()
    monkeypatch.setattr(auth, "authorize_worker_actor", AsyncMock(return_value="user"))
    worker = StandaloneWorkerService(session)
    service = GenerationStageWorkflow(
        repository=AiGenerateTaskRepository(session), owned_run=AsyncMock()
    )
    service.stage_connection = AsyncMock(return_value="llm")
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "first"))
    await worker.claim(queue, WorkerClaimRequest(worker_id="agent"))
    await worker.started(queue, WorkerTaskEventRequest(worker_id="agent"))
    await worker.progress(
        queue,
        WorkerProgressRequest(
            worker_id="agent",
            current_stage="openapi_extract",
            stage_status="waiting_review",
            config_json={"apiExtraction": {"login": {"method": "GET", "path": "/login"}}},
        ),
    )
    run = await project_standalone_execution(session, "run")
    edited = {"login": {"method": "POST", "path": "/edited"}}
    await save_api_checkpoint(
        service, run, {"stage": "openapi_extract", "configJson": {"apiExtraction": edited}}, "user"
    )
    revision = {
        "stage": "openapi_extract",
        "revisionInstruction": "补充错误场景",
        "requestId": "revise",
    }
    revised = await revise_api_stage(
        service, await project_standalone_execution(session, "run"), revision, "user"
    )
    assert revised["status"] == "pending"
    assert (
        await revise_api_stage(
            service, await project_standalone_execution(session, "run"), revision, "user"
        )
    )["runId"] == "run"
    with pytest.raises(AppError):
        await revise_api_stage(
            service,
            await project_standalone_execution(session, "run"),
            {**revision, "revisionInstruction": "不同的要求"},
            "user",
        )
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "revise"))
    claim = await worker.claim(queue, WorkerClaimRequest(worker_id="agent"))
    assert "/edited" in claim["configJson"]
    await worker.started(queue, WorkerTaskEventRequest(worker_id="agent"))
    await worker.progress(
        queue,
        WorkerProgressRequest(
            worker_id="agent",
            current_stage="openapi_extract",
            stage_status="waiting_review",
            config_json={"apiExtraction": edited},
        ),
    )
    run = await project_standalone_execution(session, "run")
    body = {"stage": "openapi_extract", "action": "approve", "requestId": "second"}
    service.stage_connection = AsyncMock(side_effect=ErrForbidden())
    with pytest.raises(AppError):
        await review_api_checkpoint(service, run, body, "user")
    assert (await project_standalone_execution(session, "run")).status == "waiting_review"
    assert db.scalar(select(WorkerTask).where(WorkerTask.task_id == "second")) is None
    service.stage_connection = AsyncMock(return_value="llm")
    result = await review_api_checkpoint(service, run, body, "user")
    assert result["runId"] == "run" and result["currentStage"] == "generate"
    replay = await review_api_checkpoint(
        service, await project_standalone_execution(session, "run"), body, "user"
    )
    assert replay["runId"] == "run"
    with pytest.raises(AppError):
        await review_api_checkpoint(
            service,
            await project_standalone_execution(session, "run"),
            {**body, "comment": "changed"},
            "user",
        )
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "second"))
    claim = await worker.claim(queue, WorkerClaimRequest(worker_id="agent"))
    assert "login" in claim["configJson"]
    await worker.started(queue, WorkerTaskEventRequest(worker_id="agent"))
    await worker.complete(
        queue, WorkerTaskEventRequest(worker_id="agent", status="failed", error_message="failed")
    )
    body = {"stage": "generate", "requestId": "third"}
    result = await retry_api_stage(
        service, await project_standalone_execution(session, "run"), body, "user"
    )
    assert result["runId"] == "run" and result["status"] == "pending"
    replay = await retry_api_stage(
        service, await project_standalone_execution(session, "run"), body, "user"
    )
    assert replay["runId"] == "run"
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "third"))
    await worker.claim(queue, WorkerClaimRequest(worker_id="agent"))
    await worker.started(queue, WorkerTaskEventRequest(worker_id="agent"))
    await worker.complete(
        queue,
        WorkerTaskEventRequest(
            worker_id="agent",
            status="success",
            result_yaml="cases:\n  - name: Login\n    method: GET\n    urlTemplate: /login\n",
            config_json={"apiExtraction": edited},
        ),
    )
    final_revision = {
        "stage": "generate",
        "revisionInstruction": "添加负例",
        "requestId": "final-revise",
    }
    result = await revise_api_stage(
        service, await project_standalone_execution(session, "run"), final_revision, "user"
    )
    assert result["currentStage"] == "generate" and result["status"] == "pending"
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "final-revise"))
    claim = await worker.claim(queue, WorkerClaimRequest(worker_id="agent"))
    assert "resultYaml" in claim["configJson"] and "apiExtraction" in claim["configJson"]
