"""Direct-stage transaction and worker/view regression tests."""

import json

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db
from support.direct_stage_storage import (
    TRACEABLE_CONFIG,
    TRACEABLE_POINTS,
    TRACEABLE_SOURCE,
    setup_stage,
)

from testing_agent.core.errors import AppError


@pytest.mark.parametrize("continue_after", [False, True])
async def test_api_stages_preserve_selection_and_import_after_parent_deletion(db, continue_after):  # noqa: F811
    from support.generation import generation_services

    from testing_agent.domain.api_interface import path_key
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.models.api_assert_rule import ApiAssertRule
    from testing_agent.models.api_case import ApiCase
    from testing_agent.models.api_collection import ApiCollection
    from testing_agent.models.api_extract_rule import ApiExtractRule
    from testing_agent.models.api_interface import ApiInterface
    from testing_agent.models.software_repository import SoftwareRepository
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.schemas.generation_chain import (
        GenerationChainImportRequest,
        GenerationChainReviewRequest,
        GenerationChainRunRequest,
    )
    from testing_agent.services.stage_storage.commands import DirectStageCommands
    from testing_agent.services.stage_storage.version_delete import delete_stage_version

    stage, storage = setup_stage(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.task_type, task.source_type, task.source_content = (
        "api_case_generate",
        "interface_library",
        "",
    )
    task.interface_ids_json = ["interface-1"]
    db.add(
        SoftwareRepository(
            software_repository_id="repository-1",
            project_id="p",
            name="订单服务",
            base_path="/api",
            repository_project_id="42",
            repository_path="commerce/order-service",
            repository_instance_url="https://gitlab.example.com",
            created_by_user_id="u",
        )
    )
    db.flush()
    db.add(
        ApiInterface(
            interface_id="interface-1",
            software_repository_id="repository-1",
            name="登录",
            method="POST",
            path="/login",
            path_key=path_key("/login"),
        )
    )
    stage.stage = "interface_extract"
    db.add_all(
        [
            ApiCollection(collection_id="target", requirement_id="r", name="目标"),
            ApiCollection(collection_id="missing-parent", requirement_id="r", name="缺失来源"),
        ]
    )
    db.commit()
    session = AsyncSessionAdapter(db)
    chain = generation_services(AiGenerateTaskRepository(session)).chain
    commands = DirectStageCommands(chain)
    first = await commands.run(
        "r", "api", "interface_extract", GenerationChainRunRequest(connectionId="llm"), "u"
    )
    first_attempt = db.get(AiGenerationAttempt, first.stages[0].active_run_id)
    await storage.publish(
        stage.id,
        attempt_id=first_attempt.id,
        worker_task_id=first_attempt.worker_task_id,
        content='{"login":{"path":"/login","method":"POST"}}',
        output_format="json",
        output_context=None,
    )
    db.commit()
    first_review = await commands.review(
        "r",
        "api",
        "interface_extract",
        GenerationChainReviewRequest(
            action="approve",
            expectedAttemptId=first_attempt.id,
            continueAfter=continue_after,
            connectionId="llm",
            instruction="覆盖鉴权异常",
        ),
        "u",
    )
    parent_id = first_review.stages[0].latest_version.version_id
    if continue_after:
        design_view = first_review
    else:
        design_view = await commands.run(
            "r",
            "api",
            "api_design",
            GenerationChainRunRequest(
                connectionId="llm",
                upstreamVersions={"interface_extract": parent_id},
            ),
            "u",
        )
    design_attempt = db.get(AiGenerationAttempt, design_view.stages[1].active_run_id)
    assert (
        design_attempt.input_snapshot_json["config"]["apiExtraction"]["login"]["path"] == "/login"
    )
    design_content = json.dumps(
        {
            "schemaVersion": "api_test_design/1.0",
            "interfaces": {
                "login": {
                    "method": "POST",
                    "path": "/login",
                    "cases": [
                        {
                            "id": "login_positive",
                            "title": "登录-正向",
                            "category": "positive",
                            "priority": "P0",
                            "intent": "验证登录成功",
                            "basis": {
                                "kind": "positive",
                                "section": "",
                                "field": "",
                                "constraint": "",
                            },
                            "patch": {},
                            "expected": {"statusClass": "2xx", "assertions": []},
                        }
                    ],
                    "uncovered": [],
                }
            },
        }
    )
    await storage.publish(
        design_attempt.stage_id,
        attempt_id=design_attempt.id,
        worker_task_id=design_attempt.worker_task_id,
        content=design_content,
        output_format="json",
        output_context=None,
    )
    db.commit()
    design_review = await commands.review(
        "r",
        "api",
        "api_design",
        GenerationChainReviewRequest(action="approve", expectedAttemptId=design_attempt.id),
        "u",
    )
    design_id = design_review.stages[1].latest_version.version_id
    generate_view = await commands.run(
        "r",
        "api",
        "generate",
        GenerationChainRunRequest(
            connectionId="llm",
            instruction="覆盖鉴权异常",
            upstreamVersions={"interface_extract": parent_id, "api_design": design_id},
        ),
        "u",
    )
    candidate = db.get(AiGenerationAttempt, generate_view.stages[2].active_run_id)
    assert candidate.input_snapshot_json["source"]["instruction"] == "覆盖鉴权异常"
    assert candidate.input_snapshot_json["config"]["apiExtraction"]["login"]["path"] == "/login"
    assert candidate.input_snapshot_json["config"]["apiDesign"] == json.loads(design_content)
    await storage.publish(
        candidate.stage_id,
        attempt_id=candidate.id,
        worker_task_id=candidate.worker_task_id,
        content=(
            "cases:\n  - name: login\n    orderNo: 1\n    method: POST\n"
            "    urlTemplate: /login\n    extractRules:\n"
            "      - {name: token, source: body_jsonpath, sourceExpr: $.token, varKey: token}\n"
            "    assertRules:\n"
            "      - {name: status, assertSource: status_code, comparator: eq, "
            "expectedValue: '200'}\n"
        ),
        output_format="yaml",
        output_context=None,
    )
    db.commit()
    approved = await commands.review(
        "r",
        "api",
        "generate",
        GenerationChainReviewRequest(action="approve", expectedAttemptId=candidate.id),
        "u",
    )
    leaf_id = approved.stages[2].latest_version.version_id
    options = await chain.import_options("r", "api", leaf_id, "u")
    assert options.parent_versions == {
        "interface_extract": parent_id,
        "api_design": design_id,
    }
    imported = await chain.import_version(
        "r", "api", leaf_id, GenerationChainImportRequest(targetId="target"), "u"
    )
    assert imported.imported and imported.changed_case_count == 1
    case = db.scalar(select(ApiCase).where(ApiCase.collection_id == "target"))
    assert db.scalar(select(ApiExtractRule).where(ApiExtractRule.case_id == case.case_id))
    assert db.scalar(select(ApiAssertRule).where(ApiAssertRule.case_id == case.case_id))
    await delete_stage_version(session, task, parent_id)
    db.commit()
    remaining = await chain.import_options("r", "api", leaf_id, "u")
    assert {item.version_id for item in remaining.parents} == {design_id}
    imported_again = await chain.import_version(
        "r", "api", leaf_id, GenerationChainImportRequest(targetId="missing-parent"), "u"
    )
    assert imported_again.imported and imported_again.changed_case_count == 1


async def test_reject_clears_unapproved_drafts_but_retains_approved_version(db):  # noqa: F811
    stage, storage = setup_stage(db)
    first = await storage.prepare(
        stage.id,
        worker_task_id="first",
        requested_by="u",
        input_snapshot={"source": {"sourceContent": "keep"}},
    )
    await storage.publish(
        stage.id,
        attempt_id=first.id,
        worker_task_id="first",
        content='{"approved":1}',
        output_format="json",
        output_context={"source": "keep"},
    )
    approved = await storage.approve(
        stage.id, expected_attempt_id=first.id, reviewer_user_id="u", comment=""
    )
    candidate = await storage.prepare(
        stage.id,
        worker_task_id="second",
        requested_by="u",
        input_snapshot={"source": {"sourceContent": "discard"}},
    )
    await storage.publish(
        stage.id,
        attempt_id=candidate.id,
        worker_task_id="second",
        content='{"discard":1}',
        output_format="json",
        output_context={"private": "discard"},
    )
    edited = await storage.save_draft(
        stage.id,
        expected_attempt_id=candidate.id,
        requested_by="u",
        content='{"discard":2}',
        output_format="json",
    )
    await storage.reject(stage.id, expected_attempt_id=edited.id)
    db.expire_all()
    assert stage.current_attempt_id is None
    assert db.get(type(first), first.id).output_content == '{"approved":1}'
    assert approved.artifact_content == '{"approved":1}'
    for attempt_id in (candidate.id, edited.id):
        attempt = db.get(type(first), attempt_id)
        assert attempt.output_content is None
        assert attempt.output_context_json is None
        assert attempt.input_snapshot_json is None


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


async def test_revision_uses_frozen_input_and_worker_receives_instruction(db, monkeypatch):  # noqa: F811
    import json
    from unittest.mock import AsyncMock

    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.services.stage_storage import authorization
    from testing_agent.services.stage_storage.payload import worker_payloads

    stage, storage = setup_stage(db)
    first = await storage.prepare(
        stage.id,
        worker_task_id="first",
        requested_by="u",
        input_snapshot={
            "llmConnectionId": "old",
            "source": {"sourceContent": "original"},
            "config": {"requirementAnalysis": {"value": "approved"}},
            "versioning": {"upstreamVersions": {"requirement_analysis": "v1"}},
        },
    )
    await storage.publish(
        stage.id,
        attempt_id=first.id,
        worker_task_id="first",
        content='{"point":1}',
        output_format="json",
        output_context=None,
    )
    revised = await storage.prepare(
        stage.id,
        worker_task_id="revision",
        requested_by="u",
        operation="revise",
        expected_attempt_id=first.id,
        revision_instruction="补充边界",
        revision_attachments=(
            {"fileId": "image-1", "filename": "x.png", "contentType": "image/png"},
        ),
        input_snapshot={"llmConnectionId": "new", "source": {"sourceContent": "tampered"}},
    )
    assert revised.input_snapshot_json["source"]["sourceContent"] == "original"
    assert revised.input_snapshot_json["versioning"]["upstreamVersions"] == {
        "requirement_analysis": "v1"
    }
    queue = WorkerTask(
        domain="ai",
        task_id="revision",
        task_type="functional_case_generate",
        run_id=revised.id,
        status="claimed",
    )
    monkeypatch.setattr(authorization, "require_project_id", AsyncMock())
    monkeypatch.setattr(authorization, "require_personal_connection", AsyncMock())
    authority = await authorization.authorize_stage_worker(AsyncSessionAdapter(db), queue)
    claim, snapshot = worker_payloads(authority, queue, stage_name=stage.stage, lease_seconds=30)
    config = json.loads(snapshot["configJson"])
    assert config["requirementAnalysis"] == {"value": "approved"}
    assert config["caseNames"] == {"point": 1}
    assert config["revisionInstruction"] == "补充边界"
    assert config["revisionAttachments"][0]["fileId"] == "image-1"
    assert claim["llmConnectionId"] == "new"
