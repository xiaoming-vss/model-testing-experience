"""Independent API checkpoint continuation shares execution and preserves inputs."""

import json
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

EXTRACTION = {
    "read_one": {
        "path": "/api/read_one",
        "method": "GET",
        "query": {"q": "string (必传) # 关键字"},
        "response": {"id": "string # [关键提取]"},
    }
}
DESIGN = {
    "schemaVersion": "api_test_design/1.0",
    "interfaces": {
        "read_one": {
            "method": "GET",
            "path": "/api/read_one",
            "cases": [
                {
                    "id": "read_one_positive_full",
                    "title": "read_one-正向-全参数",
                    "category": "positive",
                    "priority": "P0",
                    "intent": "验证完整参数查询成功",
                    "basis": {
                        "kind": "positive",
                        "section": "",
                        "field": "",
                        "constraint": "",
                    },
                    "patch": {},
                    "expected": {"statusClass": "2xx", "assertions": []},
                },
                {
                    "id": "read_one_missing_query",
                    "title": "read_one-反向-缺少查询参数",
                    "category": "negative",
                    "priority": "P1",
                    "intent": "验证缺少必填查询参数时请求被拒绝",
                    "basis": {
                        "kind": "required",
                        "section": "query",
                        "field": "/q",
                        "constraint": "required",
                    },
                    "patch": {"query": [{"op": "remove", "path": "/q"}]},
                    "expected": {"statusClass": "4xx", "assertions": []},
                },
            ],
            "uncovered": [],
        }
    },
}


def _edited_design() -> dict:
    value = json.loads(json.dumps(DESIGN))
    value["interfaces"]["read_one"]["cases"][0]["title"] = "read_one-正向-全参数-已编辑"
    return value


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
        source={"apiWorkflowVersion": "api_three_stage/1.0"},
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
            current_stage="interface_extract",
            stage_status="waiting_review",
            config_json={"apiExtraction": EXTRACTION},
        ),
    )
    run = await project_standalone_execution(session, "run")
    edited = {"read_one": {"method": "GET", "path": "/api/read_one", "query": {"q": "value"}}}
    await save_api_checkpoint(
        service,
        run,
        {"stage": "interface_extract", "configJson": {"apiExtraction": edited}},
        "user",
    )
    revision = {
        "stage": "interface_extract",
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
    assert "/api/read_one" in claim["configJson"]
    await worker.started(queue, WorkerTaskEventRequest(worker_id="agent"))
    await worker.progress(
        queue,
        WorkerProgressRequest(
            worker_id="agent",
            current_stage="interface_extract",
            stage_status="waiting_review",
            config_json={"apiExtraction": edited},
        ),
    )
    run = await project_standalone_execution(session, "run")
    body = {"stage": "interface_extract", "action": "approve", "requestId": "second"}
    service.stage_connection = AsyncMock(side_effect=ErrForbidden())
    with pytest.raises(AppError):
        await review_api_checkpoint(service, run, body, "user")
    assert (await project_standalone_execution(session, "run")).status == "waiting_review"
    assert db.scalar(select(WorkerTask).where(WorkerTask.task_id == "second")) is None
    service.stage_connection = AsyncMock(return_value="llm")
    result = await review_api_checkpoint(service, run, body, "user")
    assert result["runId"] == "run" and result["currentStage"] == "api_design"
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
    assert "read_one" in claim["configJson"]
    await worker.started(queue, WorkerTaskEventRequest(worker_id="agent"))
    await worker.complete(
        queue, WorkerTaskEventRequest(worker_id="agent", status="failed", error_message="failed")
    )
    body = {"stage": "api_design", "requestId": "third"}
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
    await worker.progress(
        queue,
        WorkerProgressRequest(
            worker_id="agent",
            current_stage="api_design",
            stage_status="waiting_review",
            config_json={"apiExtraction": edited, "apiDesign": DESIGN},
        ),
    )
    run = await project_standalone_execution(session, "run")
    assert run.current_stage == "api_design" and run.status == "waiting_review"
    edited_design = _edited_design()
    saved = await save_api_checkpoint(
        service,
        run,
        {"stage": "api_design", "configJson": {"apiDesign": edited_design}},
        "user",
    )
    assert saved["currentStage"] == "api_design"
    design_body = {"stage": "api_design", "action": "approve", "requestId": "fourth"}
    result = await review_api_checkpoint(
        service, await project_standalone_execution(session, "run"), design_body, "user"
    )
    assert result["currentStage"] == "generate"
    replay = await review_api_checkpoint(
        service, await project_standalone_execution(session, "run"), design_body, "user"
    )
    assert replay["runId"] == "run"
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "fourth"))
    claim = await worker.claim(queue, WorkerClaimRequest(worker_id="agent"))
    config = json.loads(claim["configJson"])
    assert config["apiExtraction"] == edited and config["apiDesign"] == edited_design
    await worker.started(queue, WorkerTaskEventRequest(worker_id="agent"))
    await worker.complete(
        queue,
        WorkerTaskEventRequest(
            worker_id="agent",
            status="success",
            result_yaml="cases:\n  - name: Login\n    method: GET\n    urlTemplate: /login\n",
            config_json={"apiExtraction": edited, "apiDesign": edited_design},
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
    config = json.loads(claim["configJson"])
    assert "resultYaml" in config
    assert config["apiExtraction"] == edited and config["apiDesign"] == edited_design
