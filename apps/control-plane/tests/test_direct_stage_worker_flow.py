"""Direct-stage transaction and worker/view regression tests."""

import json

import pytest
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db
from support.direct_stage_storage import (
    TRACEABLE_CONFIG,
    TRACEABLE_POINTS,
    TRACEABLE_SOURCE,
    setup_stage,
)

from testing_agent.core.errors import AppError


async def test_old_worker_cannot_overwrite_new_attempt(db):  # noqa: F811
    from testing_agent.services.stage_storage.worker import StageWorkerTransitions

    stage, storage = setup_stage(db)
    worker = StageWorkerTransitions(AsyncSessionAdapter(db))
    first = await storage.prepare(
        stage.id, worker_task_id="expired", requested_by="u", input_snapshot={}
    )
    await worker.started(stage.id, first.id, "expired")
    await worker.progress(stage.id, first.id, "expired", {"current": 1})
    await worker.failed(stage.id, first.id, "expired", error_message="失去租约")
    second = await storage.prepare(
        stage.id, worker_task_id="replacement", requested_by="u", input_snapshot={}
    )
    with pytest.raises(AppError):
        await worker.completed(
            stage.id,
            first.id,
            "expired",
            content='{"old":true}',
            output_format="json",
            output_context=None,
        )
    await worker.started(stage.id, second.id, "replacement")
    await worker.completed(
        stage.id,
        second.id,
        "replacement",
        content='{"fresh":true}',
        output_format="json",
        output_context=None,
    )
    assert stage.current_attempt_id == second.id
    assert second.output_content == '{"fresh":true}'


async def test_stage_worker_authorization_rechecks_current_actor_and_task(db, monkeypatch):  # noqa: F811
    from unittest.mock import AsyncMock

    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.services.stage_storage import authorization

    stage, storage = setup_stage(db)
    attempt = await storage.prepare(
        stage.id,
        worker_task_id="worker-new",
        requested_by="u",
        input_snapshot={"llmConnectionId": "llm", "source": {}},
    )
    queue = WorkerTask(
        domain="ai",
        task_id="worker-new",
        task_type="functional_case_generate",
        run_id=attempt.id,
        status="claimed",
    )
    project_access = AsyncMock()
    connection_access = AsyncMock()
    monkeypatch.setattr(authorization, "require_project_id", project_access)
    monkeypatch.setattr(authorization, "require_personal_connection", connection_access)
    result = await authorization.authorize_stage_worker(AsyncSessionAdapter(db), queue)
    assert result.actor_id == "u" and result.stage_id == stage.id
    project_access.assert_awaited_once()
    connection_access.assert_awaited_once()
    queue.task_id = "forged-worker"
    with pytest.raises(AppError):
        await authorization.authorize_stage_worker(AsyncSessionAdapter(db), queue)
    queue.task_id = "worker-new"
    queue.status = "failed"
    with pytest.raises(AppError):
        await authorization.authorize_stage_worker(AsyncSessionAdapter(db), queue)


async def test_stage_worker_payload_matches_both_sides_contract(db, monkeypatch):  # noqa: F811
    import sys
    from pathlib import Path
    from unittest.mock import AsyncMock

    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.schemas.workers import AiWorkerClaimPayload, WorkerSnapshotResponse
    from testing_agent.services.stage_storage import authorization
    from testing_agent.services.stage_storage.payload import worker_payloads

    stage, storage = setup_stage(db)
    attempt = await storage.prepare(
        stage.id,
        worker_task_id="worker-new",
        requested_by="u",
        input_snapshot={
            "llmConnectionId": "llm",
            "source": {"sourceType": "text", "sourceContent": "需求"},
            "config": {"requirementAnalysis": {"name": "上游"}},
        },
    )
    queue = WorkerTask(
        domain="ai",
        task_id="worker-new",
        task_type="functional_case_generate",
        run_id=attempt.id,
        status="claimed",
    )
    monkeypatch.setattr(authorization, "require_project_id", AsyncMock())
    monkeypatch.setattr(authorization, "require_personal_connection", AsyncMock())
    authority = await authorization.authorize_stage_worker(AsyncSessionAdapter(db), queue)
    claim, snapshot = worker_payloads(authority, queue, stage_name=stage.stage, lease_seconds=30)
    AiWorkerClaimPayload.model_validate(claim)
    WorkerSnapshotResponse.model_validate(snapshot)
    worker_src = Path(__file__).resolve().parents[3] / "apps/ai-worker/src"
    sys.path.insert(0, str(worker_src))
    try:
        from testing_agent_ai_worker.platform.schemas import (
            PlatformClaimTask,
            PlatformSnapshotResponse,
        )

        parsed_claim = PlatformClaimTask.model_validate(claim)
        parsed_snapshot = PlatformSnapshotResponse.model_validate(snapshot)
        assert parsed_claim.attempt_id == parsed_snapshot.run.attempt_id == attempt.id
        assert parsed_snapshot.run.source_content == "需求"
        assert parsed_claim.current_stage == parsed_snapshot.current_stage == "case_names"
    finally:
        sys.path.remove(str(worker_src))


async def test_stage_worker_progress_validates_frozen_inputs_and_waits_for_review(db):  # noqa: F811
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.schemas.workers import WorkerProgressRequest
    from testing_agent.services.stage_storage.worker import StageWorkerTransitions
    from testing_agent.services.stage_storage.worker_events import apply_stage_progress

    stage, storage = setup_stage(db)
    frozen = TRACEABLE_CONFIG.copy()
    attempt = await storage.prepare(
        stage.id, worker_task_id="worker-1", requested_by="u", input_snapshot={"config": frozen}
    )
    queue = WorkerTask(
        domain="ai",
        task_id="worker-1",
        task_type="functional_case_generate",
        run_id=attempt.id,
        worker_id="node",
        status="running",
    )
    await StageWorkerTransitions(AsyncSessionAdapter(db)).started(
        stage.id, attempt.id, queue.task_id
    )

    async def progress(config):
        await apply_stage_progress(
            AsyncSessionAdapter(db),
            queue,
            stage_id=stage.id,
            attempt_id=attempt.id,
            kind="function",
            stage="case_names",
            source=TRACEABLE_SOURCE,
            frozen_config=frozen,
            body=WorkerProgressRequest(
                worker_id="node",
                current_stage="case_names",
                stage_status="waiting_review",
                config_json=config,
            ),
        )

    with pytest.raises(AppError):
        await progress({"requirementAnalysis": {"scope": "tampered"}, "caseNames": {"name": "x"}})
    assert stage.active_attempt_id == attempt.id and stage.current_attempt_id is None
    await progress({**frozen, "caseNames": TRACEABLE_POINTS})
    assert stage.active_attempt_id is None and stage.current_attempt_id == attempt.id
    assert json.loads(attempt.output_content) == TRACEABLE_POINTS and queue.status == "success"


async def test_stage_worker_running_progress_accepts_empty_config(db):  # noqa: F811
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.schemas.workers import WorkerProgressRequest
    from testing_agent.services.stage_storage.worker import StageWorkerTransitions
    from testing_agent.services.stage_storage.worker_events import apply_stage_progress

    stage, storage = setup_stage(db)
    stage.stage = "relation_analysis"
    frozen = {
        "requirementAnalysis": {"scope": "approved"},
        "caseNames": {"items": []},
        "resultYaml": '{"cases": []}',
    }
    attempt = await storage.prepare(
        stage.id,
        worker_task_id="worker-graph",
        requested_by="u",
        input_snapshot={"config": frozen},
    )
    queue = WorkerTask(
        domain="ai",
        task_type="functional_case_generate",
        task_id="worker-graph",
        run_id=attempt.id,
        worker_id="node",
        status="running",
    )
    await StageWorkerTransitions(AsyncSessionAdapter(db)).started(
        stage.id, attempt.id, queue.task_id
    )

    # Worker 的进度上报（validation report）不带中间产物，configJson 会被解析为空对象。
    await apply_stage_progress(
        AsyncSessionAdapter(db),
        queue,
        stage_id=stage.id,
        attempt_id=attempt.id,
        kind="function",
        stage="relation_analysis",
        source={},
        frozen_config=frozen,
        body=WorkerProgressRequest(
            worker_id="node",
            current_stage="relation_analysis",
            stage_status="running",
            config_json={},
        ),
    )


async def test_direct_worker_claim_snapshot_start_and_review_handoff(db, monkeypatch):  # noqa: F811
    from unittest.mock import AsyncMock

    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.schemas.workers import (
        WorkerClaimRequest,
        WorkerProgressRequest,
        WorkerTaskEventRequest,
    )
    from testing_agent.services.stage_storage import authorization
    from testing_agent.services.stage_storage.worker_service import DirectStageWorkerService

    stage, storage = setup_stage(db)
    frozen = TRACEABLE_CONFIG.copy()
    attempt = await storage.prepare(
        stage.id,
        worker_task_id="worker-direct",
        requested_by="u",
        input_snapshot={"source": TRACEABLE_SOURCE, "config": frozen, "llmConnectionId": "llm"},
    )
    queue = WorkerTask(
        domain="ai",
        task_id="worker-direct",
        task_type="functional_case_generate",
        run_id=attempt.id,
        status="pending",
    )
    db.add(queue)
    db.commit()
    monkeypatch.setattr(authorization, "require_project_id", AsyncMock())
    monkeypatch.setattr(authorization, "require_personal_connection", AsyncMock())
    service = DirectStageWorkerService(AsyncSessionAdapter(db))
    assert await service.is_direct(queue)
    claim = await service.claim(queue, WorkerClaimRequest(worker_id="node"))
    assert claim["attemptId"] == attempt.id and queue.status == "claimed"
    snapshot = await service.snapshot(queue)
    assert snapshot["run"]["taskId"] == "task" and snapshot["currentStage"] == "case_names"
    await service.started(queue, WorkerTaskEventRequest(worker_id="node", task_id=queue.task_id))
    assert attempt.status == "running" and queue.status == "running"
    await service.progress(
        queue,
        WorkerProgressRequest(
            worker_id="node",
            task_id=queue.task_id,
            run_id=attempt.id,
            current_stage="case_names",
            stage_status="waiting_review",
            config_json={**frozen, "caseNames": TRACEABLE_POINTS},
        ),
    )
    assert queue.status == "success" and stage.current_attempt_id == attempt.id
    assert (
        stage.review_status == "pending" and json.loads(attempt.output_content) == TRACEABLE_POINTS
    )


async def test_worker_api_service_routes_direct_tasks_without_old_run_rows(db, monkeypatch):  # noqa: F811
    from unittest.mock import AsyncMock

    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.repositories.worker_task import WorkerTaskRepository
    from testing_agent.schemas.workers import (
        WorkerClaimRequest,
        WorkerProgressRequest,
        WorkerTaskEventRequest,
    )
    from testing_agent.services.stage_storage import authorization
    from testing_agent.services.worker_task import WorkerTaskService

    stage, storage = setup_stage(db)
    frozen = TRACEABLE_CONFIG.copy()
    attempt = await storage.prepare(
        stage.id,
        worker_task_id="worker-direct",
        requested_by="u",
        input_snapshot={"source": TRACEABLE_SOURCE, "config": frozen, "llmConnectionId": "llm"},
    )
    queue = WorkerTask(
        domain="ai",
        task_id="worker-direct",
        task_type="functional_case_generate",
        run_id=attempt.id,
        status="pending",
    )
    db.add(queue)
    db.commit()
    monkeypatch.setattr(authorization, "require_project_id", AsyncMock())
    monkeypatch.setattr(authorization, "require_personal_connection", AsyncMock())
    service = WorkerTaskService(WorkerTaskRepository(AsyncSessionAdapter(db)))
    claim = await service._claim_task("ai", queue, WorkerClaimRequest(worker_id="node"))
    assert claim["attemptId"] == attempt.id
    snapshot = await service.snapshot("ai", queue.task_id)
    assert snapshot["currentStage"] == "case_names"
    await service.started("ai", queue.task_id, WorkerTaskEventRequest(worker_id="node"))
    await service.progress(
        queue.task_id,
        WorkerProgressRequest(
            worker_id="node",
            task_id=queue.task_id,
            run_id=attempt.id,
            current_stage="case_names",
            stage_status="waiting_review",
            config_json={**frozen, "caseNames": TRACEABLE_POINTS},
        ),
    )
    assert queue.status == "success" and stage.current_attempt_id == attempt.id


async def test_worker_authorization_revocation_fails_only_its_current_attempt(db, monkeypatch):  # noqa: F811
    from unittest.mock import AsyncMock

    from testing_agent.core.errors import ErrForbidden
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.repositories.worker_task import WorkerTaskRepository
    from testing_agent.schemas.workers import WorkerClaimRequest
    from testing_agent.services.stage_storage import authorization
    from testing_agent.services.worker_task import WorkerTaskService

    stage, storage = setup_stage(db)
    attempt = await storage.prepare(
        stage.id,
        worker_task_id="revoked",
        requested_by="u",
        input_snapshot={"source": {}, "config": {}, "llmConnectionId": "llm"},
    )
    queue = WorkerTask(
        domain="ai",
        task_id="revoked",
        task_type="functional_case_generate",
        run_id=attempt.id,
        status="pending",
    )
    db.add(queue)
    db.commit()
    monkeypatch.setattr(authorization, "require_project_id", AsyncMock())
    monkeypatch.setattr(
        authorization, "require_personal_connection", AsyncMock(side_effect=ErrForbidden())
    )
    service = WorkerTaskService(WorkerTaskRepository(AsyncSessionAdapter(db)))
    assert await service._claim_task("ai", queue, WorkerClaimRequest(worker_id="node")) is None
    assert queue.status == "failed" and attempt.status == "failed"
    assert stage.active_attempt_id is None and attempt.status == "failed"
