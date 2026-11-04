"""Auxiliary AI results use the same attempt identity and Worker lifecycle."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.worker_task import WorkerTask
from testing_agent.schemas.workers import (
    AiWorkerClaimPayload,
    WorkerClaimRequest,
    WorkerProgressRequest,
    WorkerSnapshotResponse,
    WorkerTaskEventRequest,
)
from testing_agent.services.stage_storage.dispatch import dispatch_stage_attempt
from testing_agent.services.stage_storage.worker_service import DirectStageWorkerService

# The Worker is an independent project. This contract test reads its protocol
# models directly; only the standard-library path injection is shared.
WORKER_SRC = Path(__file__).resolve().parents[2] / "ai-worker" / "src"
if str(WORKER_SRC) not in sys.path:
    sys.path.insert(0, str(WORKER_SRC))


@pytest.mark.parametrize(
    "task_type", ["code_risk_analysis", "test_report_generate", "test_order_graph"]
)
async def test_auxiliary_worker_claim_progress_and_result(db, monkeypatch, task_type):  # noqa: F811
    from testing_agent.services.stage_storage import authorization

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.task_type = task_type
    stage = AiGenerationStage(id="auxiliary", task_id=task.task_id, stage="generate")
    db.add(stage)
    db.commit()
    session = AsyncSessionAdapter(db)
    attempt, _ = await dispatch_stage_attempt(
        session,
        task=task,
        stage_id=stage.id,
        request_id="dispatch-aux",
        actor_id="u",
        input_snapshot={
            "source": {"example": "frozen", "name": "original name"},
            "config": {},
            "llmConnectionId": "llm",
        },
        review_required=False,
    )
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "dispatch-aux"))
    task.name = "changed after dispatch"
    db.commit()
    monkeypatch.setattr(authorization, "require_project_id", AsyncMock())
    monkeypatch.setattr(authorization, "require_personal_connection", AsyncMock())
    service = DirectStageWorkerService(session)
    claim = await service.claim(queue, WorkerClaimRequest(worker_id="worker"))
    assert attempt.status == "claimed"
    assert claim["attemptId"] == attempt.id != attempt.execution_id
    assert claim["checkpointEnabled"] is False
    assert claim["currentStage"] == ("generate" if task_type == "test_order_graph" else "")
    detail = await service.snapshot(queue)
    AiWorkerClaimPayload.model_validate(claim)
    WorkerSnapshotResponse.model_validate(detail)
    from testing_agent_ai_worker.platform.schemas import PlatformClaimTask, PlatformSnapshotResponse

    assert PlatformClaimTask.model_validate(claim).attempt_id == attempt.id
    assert PlatformSnapshotResponse.model_validate(detail).run.attempt_id == attempt.id
    assert detail["run"]["example"] == "frozen"
    assert detail["run"]["name"] == "original name"
    with pytest.raises(AppError):
        await service.started(
            queue, WorkerTaskEventRequest(worker_id="worker", run_id="wrong-attempt")
        )
    await service.started(queue, WorkerTaskEventRequest(worker_id="worker", run_id=attempt.id))
    await service.progress(
        queue,
        WorkerProgressRequest(
            worker_id="worker",
            run_id=attempt.id,
            current_stage="worker-internal-stage",
            stage_status="running",
            result_summary_json={"detail": "do not persist"},
        ),
    )
    assert attempt.status == "running"
    assert attempt.output_context_json is None
    await service.complete(
        queue,
        WorkerTaskEventRequest(
            worker_id="worker", run_id=attempt.id, status="success", output_yaml="result"
        ),
    )
    assert queue.status == attempt.status == "success"
    assert attempt.output_content == "result"
    assert stage.review_status == "not_required"
    with pytest.raises(AppError):
        await service.complete(
            queue,
            WorkerTaskEventRequest(
                worker_id="worker", run_id=attempt.id, status="success", output_yaml="late"
            ),
        )
    assert attempt.output_content == "result"


@pytest.mark.parametrize("status", ["failed", "error", "canceled"])
async def test_auxiliary_worker_error_preserves_previous_result(db, status):  # noqa: F811
    from testing_agent.services.stage_storage import DirectStageStorage
    from testing_agent.services.stage_storage.worker import StageWorkerTransitions
    from testing_agent.services.stage_storage.worker_events import apply_auxiliary_completion

    seed_task(db)
    stage = AiGenerationStage(id="auxiliary", task_id="task", stage="generate")
    db.add(stage)
    db.commit()
    session = AsyncSessionAdapter(db)
    storage = DirectStageStorage(session)
    previous = await storage.prepare(
        stage.id,
        worker_task_id="previous",
        requested_by="u",
        input_snapshot={},
        review_required=False,
    )
    await storage.publish(
        stage.id,
        attempt_id=previous.id,
        worker_task_id="previous",
        content="old success",
        output_format="text",
        output_context=None,
    )
    current = await storage.prepare(
        stage.id,
        worker_task_id="current",
        requested_by="u",
        input_snapshot={},
        review_required=False,
    )
    queue = WorkerTask(
        domain="ai",
        task_id="current",
        task_type="test_order_graph",
        run_id=current.id,
        status="running",
        worker_id="worker",
    )
    db.add(queue)
    await StageWorkerTransitions(session).started(stage.id, current.id, queue.task_id)
    await apply_auxiliary_completion(
        session,
        queue,
        stage_id=stage.id,
        attempt_id=current.id,
        body=WorkerTaskEventRequest(
            worker_id="worker", status=status, error_message="error details"
        ),
    )
    assert queue.status == current.status == status
    assert current.error_message == "error details"
    assert stage.current_attempt_id == previous.id
    assert previous.output_content == "old success"
    assert stage.active_attempt_id is None


async def test_code_risk_credentials_use_attempt_actor_and_frozen_bindings(
    db,  # noqa: F811
    monkeypatch,
):
    from types import SimpleNamespace

    from testing_agent.repositories.worker_task import WorkerTaskRepository
    from testing_agent.services import worker_task as worker_task_module
    from testing_agent.services.stage_storage import DirectStageStorage, authorization
    from testing_agent.services.worker_task import WorkerTaskService

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.task_type = "code_risk_analysis"
    stage = AiGenerationStage(id="risk-stage", task_id=task.task_id, stage="generate")
    db.add(stage)
    db.commit()
    session = AsyncSessionAdapter(db)
    bindings = [
        {"connectionId": "gitlab", "instanceUrl": "https://gitlab.example", "repositoryId": "repo"}
    ]
    attempt = await DirectStageStorage(session).prepare(
        stage.id,
        worker_task_id="risk-worker",
        requested_by="u",
        review_required=False,
        input_snapshot={"source": {"bindings": bindings}, "config": {}, "llmConnectionId": "llm"},
    )
    queue = WorkerTask(
        domain="ai",
        task_id="risk-worker",
        task_type="code_risk_analysis",
        run_id=attempt.id,
        status="claimed",
        worker_id="worker",
    )
    db.add(queue)
    db.commit()
    monkeypatch.setattr(authorization, "require_project_id", AsyncMock())
    monkeypatch.setattr(
        authorization,
        "require_personal_connection",
        AsyncMock(return_value=SimpleNamespace(base_url="https://gitlab.example")),
    )
    monkeypatch.setattr(worker_task_module, "find_task", AsyncMock(return_value=queue))
    payload = AsyncMock(return_value={"taskId": "risk-worker", "credentials": []})
    monkeypatch.setattr(worker_task_module, "gitlab_credentials_payload", payload)
    result = await WorkerTaskService(WorkerTaskRepository(session)).gitlab_credentials(
        "risk-worker"
    )
    assert result["taskId"] == "risk-worker"
    assert payload.await_args.args[2:4] == ("p", bindings)
    assert payload.await_args.kwargs["user_id"] == "u"


async def test_code_risk_attempt_can_read_its_requirement_document(db, monkeypatch):  # noqa: F811
    from testing_agent.models.requirement import Requirement
    from testing_agent.repositories.worker_task import WorkerTaskRepository
    from testing_agent.services.stage_storage import DirectStageStorage, authorization
    from testing_agent.services.worker_task import WorkerTaskService

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.task_type = "code_risk_analysis"
    requirement = db.scalar(select(Requirement).where(Requirement.requirement_id == "r"))
    requirement.document_file_id = "original-document"
    stage = AiGenerationStage(id="risk-document-stage", task_id="task", stage="generate")
    db.add(stage)
    db.commit()
    session = AsyncSessionAdapter(db)
    attempt = await DirectStageStorage(session).prepare(
        stage.id,
        worker_task_id="risk-document-worker",
        requested_by="u",
        review_required=False,
        input_snapshot={"source": {"bindings": []}, "config": {}, "llmConnectionId": "llm"},
    )
    db.add(
        WorkerTask(
            domain="ai",
            task_id="risk-document-worker",
            task_type="code_risk_analysis",
            run_id=attempt.id,
            status="claimed",
            worker_id="worker",
        )
    )
    db.commit()
    monkeypatch.setattr(authorization, "require_project_id", AsyncMock())
    monkeypatch.setattr(authorization, "require_personal_connection", AsyncMock())
    result = await WorkerTaskService(WorkerTaskRepository(session)).requirement_document(
        "risk-document-worker"
    )
    assert result.requirement_id == "r" and result.document_file_id == "original-document"


async def test_worker_rejects_attempt_whose_task_scope_no_longer_matches(db, monkeypatch):  # noqa: F811
    from testing_agent.models.project import Project
    from testing_agent.services.stage_storage import DirectStageStorage, authorization

    seed_task(db)
    db.add(Project(project_id="other-project", user_id="u", name="other"))
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.task_type = "code_risk_analysis"
    task.project_id = "other-project"
    stage = AiGenerationStage(id="risk-invalid-scope", task_id="task", stage="generate")
    db.add(stage)
    db.commit()
    session = AsyncSessionAdapter(db)
    attempt = await DirectStageStorage(session).prepare(
        stage.id,
        worker_task_id="invalid-scope-worker",
        requested_by="u",
        review_required=False,
        input_snapshot={"source": {}, "config": {}, "llmConnectionId": "llm"},
    )
    queue = WorkerTask(
        domain="ai",
        task_id="invalid-scope-worker",
        task_type="code_risk_analysis",
        run_id=attempt.id,
        status="claimed",
        worker_id="worker",
    )
    db.add(queue)
    db.commit()
    monkeypatch.setattr(authorization, "require_project_id", AsyncMock())
    monkeypatch.setattr(authorization, "require_personal_connection", AsyncMock())
    with pytest.raises(AppError):
        await authorization.authorize_stage_worker(session, queue)
