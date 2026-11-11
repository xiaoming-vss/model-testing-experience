"""Direct-stage transaction prototype."""

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.services.stage_storage import DirectStageStorage


def setup_stage(session):
    seed_task(session)
    stage = AiGenerationStage(
        id="stage-direct", task_id="task", stage="case_names", next_version_no=1
    )
    session.add(stage)
    session.commit()
    return stage, DirectStageStorage(AsyncSessionAdapter(session))


async def test_unconfigured_chain_view_does_not_create_stages(db):  # noqa: F811
    from testing_agent.services.stage_storage.chain_view import build_chain_view

    seed_task(db)
    before = len(db.scalars(select(AiGenerationStage)).all())
    view = await build_chain_view(AsyncSessionAdapter(db), "r", "api", None, detail=True)
    assert [stage.stage for stage in view.stages] == ["openapi_extract", "generate"]
    assert not view.configured
    assert len(db.scalars(select(AiGenerationStage)).all()) == before


async def test_requirement_document_runs_and_reviews_as_two_independent_stages(db):  # noqa: F811
    import json

    from support.generation import generation_services
    from support.requirement_analysis import example

    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.models.requirement import Requirement
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.schemas.generation_chain import (
        GenerationChainReviewRequest,
        GenerationChainRunRequest,
    )
    from testing_agent.services.stage_storage.commands import DirectStageCommands

    stage, storage = setup_stage(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    requirement = db.scalar(select(Requirement).where(Requirement.requirement_id == "r"))
    task.task_type, stage.stage = "requirement_analysis", "extracting_text"
    db.commit()
    session = AsyncSessionAdapter(db)
    chain = generation_services(AiGenerateTaskRepository(session)).chain
    commands = DirectStageCommands(chain)
    with pytest.raises(AppError):
        await commands.run(
            "r",
            "requirement_analysis",
            "extracting_text",
            GenerationChainRunRequest(connectionId="llm"),
            "u",
        )
    db.rollback()
    requirement.document_file_id = "document-file"
    db.commit()
    first = await commands.run(
        "r",
        "requirement_analysis",
        "extracting_text",
        GenerationChainRunRequest(connectionId="llm"),
        "u",
    )
    extracting = db.get(AiGenerationAttempt, first.stages[0].active_run_id)
    assert extracting.input_snapshot_json["source"]["documentFileId"] == "document-file"
    assert extracting.input_snapshot_json["source"]["workflowVersion"] == 2
    await storage.publish(
        stage.id,
        attempt_id=extracting.id,
        worker_task_id=extracting.worker_task_id,
        content=json.dumps(example("document-extraction"), ensure_ascii=False),
        output_format="json",
        output_context=None,
    )
    db.commit()
    approved = await commands.review(
        "r",
        "requirement_analysis",
        "extracting_text",
        GenerationChainReviewRequest(
            action="approve",
            expectedAttemptId=extracting.id,
            continueAfter=True,
            connectionId="llm",
        ),
        "u",
    )
    first_version = approved.stages[0].latest_version.version_id
    understanding = db.get(AiGenerationAttempt, approved.stages[1].active_run_id)
    assert understanding.input_snapshot_json["versioning"]["upstreamVersions"] == {
        "extracting_text": first_version
    }
    await storage.publish(
        understanding.stage_id,
        attempt_id=understanding.id,
        worker_task_id=understanding.worker_task_id,
        content=json.dumps(example("requirement-understanding"), ensure_ascii=False),
        output_format="json",
        output_context=None,
    )
    db.commit()
    final = await commands.review(
        "r",
        "requirement_analysis",
        "feature_understanding",
        GenerationChainReviewRequest(action="approve", expectedAttemptId=understanding.id),
        "u",
    )
    assert final.stages[1].state == "approved"


async def test_direct_attempt_isolated_edit_then_immutable_version(db):  # noqa: F811
    stage, storage = setup_stage(db)
    attempt = await storage.prepare(
        stage.id,
        worker_task_id="worker-1",
        requested_by="u",
        input_snapshot={"versioning": {"upstreamVersions": {"requirement_analysis": "old"}}},
    )
    with pytest.raises(AppError):
        await storage.prepare(
            stage.id, worker_task_id="worker-2", requested_by="u", input_snapshot={}
        )
    with pytest.raises(AppError):
        await storage.publish(
            stage.id,
            attempt_id=attempt.id,
            worker_task_id="other",
            content="{}",
            output_format="json",
            output_context=None,
        )
    await storage.publish(
        stage.id,
        attempt_id=attempt.id,
        worker_task_id="worker-1",
        content='{"old":true}',
        output_format="json",
        output_context=None,
    )
    edit = await storage.save_draft(
        stage.id,
        expected_attempt_id=attempt.id,
        requested_by="u",
        content='{"new":true}',
        output_format="json",
    )
    with pytest.raises(AppError):
        await storage.approve(
            stage.id, expected_attempt_id=attempt.id, reviewer_user_id="u", comment="ok"
        )
    version = await storage.approve(
        stage.id, expected_attempt_id=edit.id, reviewer_user_id="u", comment="ok"
    )
    assert (version.artifact_content, version.upstream_versions_json, version.version_no) == (
        '{"new":true}',
        {"requirement_analysis": "old"},
        1,
    )
    with pytest.raises(AppError):
        await storage.save_draft(
            stage.id,
            expected_attempt_id=edit.id,
            requested_by="u",
            content='{"late":true}',
            output_format="json",
        )
    assert (
        db.scalar(select(AiGenerationStage.next_version_no).where(AiGenerationStage.id == stage.id))
        == 2
    )


async def test_deleted_version_number_is_not_reused(db):  # noqa: F811
    """Removing an approved version must not rewind the stage's version sequence."""
    from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion

    stage, storage = setup_stage(db)
    attempt = await storage.prepare(
        stage.id, worker_task_id="first", requested_by="u", input_snapshot={}
    )
    await storage.publish(
        stage.id,
        attempt_id=attempt.id,
        worker_task_id="first",
        content='{"first":1}',
        output_format="json",
        output_context=None,
    )
    first = await storage.approve(
        stage.id, expected_attempt_id=attempt.id, reviewer_user_id="u", comment=""
    )
    assert first.version_no == 1
    db.commit()
    db.delete(db.get(AiGenerateStageVersion, first.id))
    db.commit()
    next_attempt = await storage.prepare(
        stage.id, worker_task_id="second", requested_by="u", input_snapshot={}
    )
    await storage.publish(
        stage.id,
        attempt_id=next_attempt.id,
        worker_task_id="second",
        content='{"next":1}',
        output_format="json",
        output_context=None,
    )
    second = await storage.approve(
        stage.id, expected_attempt_id=next_attempt.id, reviewer_user_id="u", comment=""
    )
    assert second.version_no == 2


async def test_failed_version_write_rolls_back_review(db):  # noqa: F811
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion

    stage, storage = setup_stage(db)
    attempt = await storage.prepare(
        stage.id, worker_task_id="worker", requested_by="u", input_snapshot={}
    )
    await storage.publish(
        stage.id,
        attempt_id=attempt.id,
        worker_task_id="worker",
        content='{"draft":1}',
        output_format="json",
        output_context=None,
    )
    db.commit()
    db.execute(
        text("""
        CREATE TRIGGER fail_version_insert BEFORE INSERT ON ai_generate_stage_versions
        BEGIN SELECT RAISE(ABORT, 'version write failed'); END
    """)
    )
    db.commit()
    with pytest.raises(IntegrityError):
        await storage.approve(
            stage.id, expected_attempt_id=attempt.id, reviewer_user_id="u", comment="approved"
        )
    db.rollback()
    db.expire_all()
    current = db.get(AiGenerationStage, stage.id)
    assert current.review_status == "pending"
    assert current.current_attempt_id == attempt.id
    assert current.next_version_no == 1
    assert db.scalar(select(AiGenerateStageVersion)) is None


async def test_new_upstream_version_does_not_change_approved_downstream(db):  # noqa: F811
    from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.services.stage_storage.chain_view import build_chain_view

    downstream, storage = setup_stage(db)
    upstream = AiGenerationStage(
        id="analysis-direct", task_id="task", stage="requirement_analysis", next_version_no=1
    )
    db.add(upstream)
    db.commit()

    async def approve(stage, worker, content, snapshot):
        attempt = await storage.prepare(
            stage.id, worker_task_id=worker, requested_by="u", input_snapshot=snapshot
        )
        await storage.publish(
            stage.id,
            attempt_id=attempt.id,
            worker_task_id=worker,
            content=content,
            output_format="json",
            output_context=None,
        )
        return await storage.approve(
            stage.id, expected_attempt_id=attempt.id, reviewer_user_id="u", comment=""
        )

    original = await approve(upstream, "upstream-v1", '{"purpose":"first"}', {})
    leaf = await approve(
        downstream,
        "downstream",
        '{"points":["first"]}',
        {"versioning": {"upstreamVersions": {"requirement_analysis": original.version_id}}},
    )
    db.commit()
    newer = await approve(upstream, "upstream-v2", '{"purpose":"second"}', {})
    db.commit()
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    view = await build_chain_view(AsyncSessionAdapter(db), "r", "function", task, detail=True)
    stage = next(item for item in view.stages if item.stage == "case_names")
    assert newer.version_no == 2
    assert stage.state == "approved"
    assert stage.latest_version.version_id == leaf.version_id
    persisted = db.scalar(
        select(AiGenerateStageVersion).where(AiGenerateStageVersion.version_id == leaf.version_id)
    )
    assert persisted.artifact_content == '{"points":["first"]}'
    assert persisted.upstream_versions_json == {"requirement_analysis": original.version_id}


async def test_one_stage_can_run_while_another_draft_is_edited(db):  # noqa: F811
    draft_stage, storage = setup_stage(db)
    running_stage = AiGenerationStage(
        id="running-stage", task_id="task", stage="detailed_cases", next_version_no=1
    )
    db.add(running_stage)
    db.commit()
    draft = await storage.prepare(
        draft_stage.id, worker_task_id="draft-worker", requested_by="u", input_snapshot={}
    )
    await storage.publish(
        draft_stage.id,
        attempt_id=draft.id,
        worker_task_id="draft-worker",
        content='{"point":1}',
        output_format="json",
        output_context=None,
    )
    running = await storage.prepare(
        running_stage.id, worker_task_id="running-worker", requested_by="u", input_snapshot={}
    )
    edited = await storage.save_draft(
        draft_stage.id,
        expected_attempt_id=draft.id,
        requested_by="u",
        content='{"point":2}',
        output_format="json",
    )
    version = await storage.approve(
        draft_stage.id, expected_attempt_id=edited.id, reviewer_user_id="u", comment=""
    )
    assert version.artifact_content == '{"point":2}'
    assert running_stage.active_attempt_id == running.id
    assert running.status == "pending"


async def test_import_records_approved_parent_versions_and_formal_target(db):  # noqa: F811
    from support.generation import generation_services

    from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
    from testing_agent.models.function_test_case import FunctionTestCase
    from testing_agent.models.function_test_suite import FunctionTestSuite
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.schemas.generation_chain import GenerationChainImportRequest

    points, storage = setup_stage(db)
    analysis = AiGenerationStage(
        id="analysis", task_id="task", stage="requirement_analysis", next_version_no=1
    )
    leaf = AiGenerationStage(id="cases", task_id="task", stage="detailed_cases", next_version_no=1)
    db.add_all([analysis, leaf])
    db.commit()

    async def approve(stage, worker, content, fmt, upstream):
        attempt = await storage.prepare(
            stage.id,
            worker_task_id=worker,
            requested_by="u",
            input_snapshot={"source": {}, "versioning": {"upstreamVersions": upstream}},
        )
        await storage.publish(
            stage.id,
            attempt_id=attempt.id,
            worker_task_id=worker,
            content=content,
            output_format=fmt,
            output_context=None,
        )
        return await storage.approve(
            stage.id, expected_attempt_id=attempt.id, reviewer_user_id="u", comment="ok"
        )

    first = await approve(analysis, "first", '{"purpose":"login"}', "json", {})
    second = await approve(
        points, "second", '{"points":["login"]}', "json", {"requirement_analysis": first.version_id}
    )
    final = await approve(
        leaf,
        "third",
        "cases:\n  - module: 登录\n    title: 登录成功\n"
        "    preconditions: 已注册账号\n    steps: 输入正确账号密码\n"
        "    expected_results: 进入首页\n    priority: P0\n    case_type: smoke\n",
        "yaml",
        {"case_names": second.version_id},
    )
    db.commit()
    chain = generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(db))).chain
    result = await chain.import_version(
        "r", "function", final.version_id, GenerationChainImportRequest(confirmOverwrite=True), "u"
    )
    record = db.scalar(select(AiGenerateVersionImport))
    suite = db.scalar(
        select(FunctionTestSuite).where(FunctionTestSuite.suite_id == record.target_id)
    )
    assert result.imported and db.scalar(select(FunctionTestCase)).title == "登录成功"
    assert suite.effective_import_id == record.import_id
    assert record.parent_versions_json == {
        "requirement_analysis": first.version_id,
        "case_names": second.version_id,
    }


@pytest.mark.parametrize("continue_after", [False, True])
async def test_api_stages_preserve_selection_and_import_after_parent_deletion(db, continue_after):  # noqa: F811
    from support.generation import generation_services

    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.models.api_assert_rule import ApiAssertRule
    from testing_agent.models.api_case import ApiCase
    from testing_agent.models.api_collection import ApiCollection
    from testing_agent.models.api_extract_rule import ApiExtractRule
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
        "openapi",
        '{"openapi":"3.0.0","paths":{}}',
    )
    stage.stage = "openapi_extract"
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
        "r", "api", "openapi_extract", GenerationChainRunRequest(connectionId="llm"), "u"
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
        "openapi_extract",
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
        second = first_review
    else:
        second = await commands.run(
            "r",
            "api",
            "generate",
            GenerationChainRunRequest(
                connectionId="llm",
                instruction="覆盖鉴权异常",
                upstreamVersions={"openapi_extract": parent_id},
            ),
            "u",
        )
    candidate = db.get(AiGenerationAttempt, second.stages[1].active_run_id)
    assert candidate.input_snapshot_json["source"]["instruction"] == "覆盖鉴权异常"
    assert candidate.input_snapshot_json["config"]["apiExtraction"]["login"]["path"] == "/login"
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
    leaf_id = approved.stages[1].latest_version.version_id
    options = await chain.import_options("r", "api", leaf_id, "u")
    assert options.parent_versions == {"openapi_extract": parent_id}
    imported = await chain.import_version(
        "r", "api", leaf_id, GenerationChainImportRequest(targetId="target"), "u"
    )
    assert imported.imported and imported.changed_case_count == 1
    case = db.scalar(select(ApiCase).where(ApiCase.collection_id == "target"))
    assert db.scalar(select(ApiExtractRule).where(ApiExtractRule.case_id == case.case_id))
    assert db.scalar(select(ApiAssertRule).where(ApiAssertRule.case_id == case.case_id))
    await delete_stage_version(session, task, parent_id)
    db.commit()
    assert (await chain.import_options("r", "api", leaf_id, "u")).parents == []
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
    frozen = {"requirementAnalysis": {"scope": "approved"}}
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
            source={},
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
    await progress({"requirementAnalysis": {"scope": "approved"}, "caseNames": {"name": "x"}})
    assert stage.active_attempt_id is None and stage.current_attempt_id == attempt.id
    assert attempt.output_content == '{"name": "x"}' and queue.status == "success"


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
    frozen = {"requirementAnalysis": {"scope": "approved"}}
    attempt = await storage.prepare(
        stage.id,
        worker_task_id="worker-direct",
        requested_by="u",
        input_snapshot={"source": {}, "config": frozen, "llmConnectionId": "llm"},
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
            config_json={**frozen, "caseNames": {"name": "point"}},
        ),
    )
    assert queue.status == "success" and stage.current_attempt_id == attempt.id
    assert stage.review_status == "pending" and attempt.output_content == '{"name": "point"}'


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
    frozen = {"requirementAnalysis": {"scope": "approved"}}
    attempt = await storage.prepare(
        stage.id,
        worker_task_id="worker-direct",
        requested_by="u",
        input_snapshot={"source": {}, "config": frozen, "llmConnectionId": "llm"},
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
            config_json={**frozen, "caseNames": {"name": "point"}},
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


async def test_revision_attachment_ticket_only_accepts_frozen_file(db, monkeypatch):  # noqa: F811
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.repositories.worker_task import WorkerTaskRepository
    from testing_agent.services.revision_attachment_access import revision_attachment_ticket
    from testing_agent.services.stage_storage import authorization
    from testing_agent.services.worker_task import WorkerTaskService

    stage, storage = setup_stage(db)
    first = await storage.prepare(
        stage.id,
        worker_task_id="first",
        requested_by="u",
        input_snapshot={"source": {}, "config": {}, "llmConnectionId": "llm"},
    )
    await storage.publish(
        stage.id,
        attempt_id=first.id,
        worker_task_id="first",
        content='{"x":1}',
        output_format="json",
        output_context=None,
    )
    revision = await storage.prepare(
        stage.id,
        worker_task_id="revision",
        requested_by="u",
        operation="revise",
        expected_attempt_id=first.id,
        revision_instruction="修改",
        revision_attachments=(
            {"fileId": "allowed", "filename": "x.png", "contentType": "image/png"},
        ),
        input_snapshot={"llmConnectionId": "llm"},
    )
    queue = WorkerTask(
        domain="ai",
        task_id="revision",
        task_type="functional_case_generate",
        run_id=revision.id,
        status="running",
        worker_id="node",
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )
    db.add(queue)
    db.commit()
    monkeypatch.setattr(authorization, "require_project_id", AsyncMock())
    monkeypatch.setattr(authorization, "require_personal_connection", AsyncMock())
    image = SimpleNamespace(
        project_id="p",
        resource_type="ai_generate_run",
        resource_id=revision.id,
        purpose="attachment",
        status="attached",
        content_type="image/png",
    )
    files = SimpleNamespace(
        get=AsyncMock(return_value=image), ticket=AsyncMock(return_value={"ok": True})
    )
    service = WorkerTaskService(WorkerTaskRepository(AsyncSessionAdapter(db)))
    assert await revision_attachment_ticket(queue.task_id, "allowed", "node", service, files) == {
        "ok": True
    }
    with pytest.raises(AppError):
        await revision_attachment_ticket(queue.task_id, "other", "node", service, files)
    with pytest.raises(AppError):
        await revision_attachment_ticket(queue.task_id, "allowed", "other-node", service, files)


async def test_new_ui_version_freezes_source_without_old_run_lookup(db):  # noqa: F811
    from testing_agent.models.ai_generate_task import AiGenerateTask

    stage, storage = setup_stage(db)
    db.scalar(
        select(AiGenerateTask).where(AiGenerateTask.task_id == stage.task_id)
    ).task_type = "ui_case_generate"
    stage.stage = "ui_yaml"
    source = {
        "sourceKind": "repository",
        "sourceProfileVersionId": "profile-attempt-1",
        "sourceProfileVersionNo": 1,
        "sourceRepository": {
            "repositoryId": "repo-front",
            "pathWithNamespace": "team/repo-front",
            "branch": "main",
            "commit": "sha-profile",
            "commitMode": "profile",
        },
        "functionalCases": [{"caseId": "case-1", "content": "approved"}],
        "uiSourceBatchId": "batch-1",
    }
    attempt = await storage.prepare(
        stage.id, worker_task_id="ui-worker", requested_by="u", input_snapshot={"source": source}
    )
    await storage.publish(
        stage.id,
        attempt_id=attempt.id,
        worker_task_id="ui-worker",
        content="- name: test",
        output_format="yaml",
        output_context=None,
    )
    version = await storage.approve(
        stage.id, expected_attempt_id=attempt.id, reviewer_user_id="u", comment="ok"
    )
    source["functionalCases"][0]["content"] = "later change"
    assert version.artifact_context_json["uiSourceBatchId"] == "batch-1"
    assert version.artifact_context_json["uiSourceInputs"]["repository"]["commit"] == "sha-profile"
    assert version.artifact_context_json["uiSourceInputs"]["cases"][0]["content"] == "approved"


async def test_direct_requirement_worker_refuses_changed_source_document(db, monkeypatch):  # noqa: F811
    from unittest.mock import AsyncMock

    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.requirement import Requirement
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.repositories.worker_task import WorkerTaskRepository
    from testing_agent.services.stage_storage import authorization
    from testing_agent.services.worker_task import WorkerTaskService

    stage, storage = setup_stage(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == stage.task_id))
    task.task_type = "requirement_analysis"
    stage.stage = "extracting_text"
    requirement = db.scalar(select(Requirement).where(Requirement.requirement_id == "r"))
    requirement.document_file_id = "file-1"
    requirement.document_hash = "same"
    attempt = await storage.prepare(
        stage.id,
        worker_task_id="doc-worker",
        requested_by="u",
        input_snapshot={
            "source": {"workflowVersion": 2, "documentFileId": "file-1", "documentHash": "same"},
            "config": {},
            "llmConnectionId": "llm",
        },
    )
    queue = WorkerTask(
        domain="ai",
        task_id="doc-worker",
        task_type="requirement_analysis",
        run_id=attempt.id,
        status="claimed",
    )
    db.add(queue)
    db.commit()
    monkeypatch.setattr(authorization, "require_project_id", AsyncMock())
    monkeypatch.setattr(authorization, "require_personal_connection", AsyncMock())
    service = WorkerTaskService(WorkerTaskRepository(AsyncSessionAdapter(db)))
    assert (await service.requirement_document(queue.task_id)).document_file_id == "file-1"
    requirement.document_hash = "different"
    db.flush()
    with pytest.raises(AppError):
        await service.requirement_document(queue.task_id)


async def test_dispatch_retry_reuses_queue_and_attempt(db):  # noqa: F811
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.services.stage_storage.dispatch import dispatch_stage_attempt

    stage, _ = setup_stage(db)
    adapter = AsyncSessionAdapter(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == stage.task_id))
    original, reused = await dispatch_stage_attempt(
        adapter,
        task=task,
        stage_id=stage.id,
        request_id="request-1",
        actor_id="u",
        input_snapshot={"source": {}, "config": {}, "llmConnectionId": "llm"},
    )
    again, repeated = await dispatch_stage_attempt(
        adapter,
        task=task,
        stage_id=stage.id,
        request_id="request-1",
        actor_id="u",
        input_snapshot={"source": {}, "config": {}, "llmConnectionId": "llm"},
    )
    assert not reused and repeated and again.id == original.id
    queues = db.scalars(select(WorkerTask).where(WorkerTask.task_id == "request-1")).all()
    assert len(queues) == 1 and queues[0].run_id == original.id
    with pytest.raises(AppError):
        await dispatch_stage_attempt(
            adapter,
            task=task,
            stage_id=stage.id,
            request_id="request-1",
            actor_id="other",
            input_snapshot={},
        )
    with pytest.raises(AppError):
        await dispatch_stage_attempt(
            adapter,
            task=task,
            stage_id=stage.id,
            request_id="different-request",
            actor_id="u",
            input_snapshot={},
        )
    assert db.scalar(select(WorkerTask).where(WorkerTask.task_id == "different-request")) is None


async def test_dispatch_rolls_back_queue_and_stage_together(db):  # noqa: F811
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.services.stage_storage.dispatch import dispatch_stage_attempt

    stage, _ = setup_stage(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == stage.task_id))
    attempt, _ = await dispatch_stage_attempt(
        AsyncSessionAdapter(db),
        task=task,
        stage_id=stage.id,
        request_id="roll-back",
        actor_id="u",
        input_snapshot={},
    )
    attempt_id = attempt.id
    db.rollback()
    db.expire_all()
    assert db.get(AiGenerationStage, stage.id).active_attempt_id is None
    assert db.get(AiGenerationAttempt, attempt_id) is None
    assert db.scalar(select(WorkerTask).where(WorkerTask.task_id == "roll-back")) is None


async def test_stage_view_reads_direct_draft_versions_and_active_attempt(db):  # noqa: F811
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.services.stage_storage.views import build_stage_views

    stage, storage = setup_stage(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == stage.task_id))
    first = await storage.prepare(
        stage.id,
        worker_task_id="first",
        requested_by="u",
        input_snapshot={"source": {}, "config": {}},
    )
    result = await build_stage_views(AsyncSessionAdapter(db), task, "function", detail=True)
    point = next(row for row in result.stages if row.stage == "case_names")
    assert point.state == "running" and result.busy and point.active_run_id == first.id
    await storage.publish(
        stage.id,
        attempt_id=first.id,
        worker_task_id="first",
        content='{"points":[1]}',
        output_format="json",
        output_context=None,
    )
    result = await build_stage_views(AsyncSessionAdapter(db), task, "function", detail=True)
    point = next(row for row in result.stages if row.stage == "case_names")
    assert (
        point.state == "draft"
        and result.draft_count == 1
        and point.draft.content == '{"points":[1]}'
    )
    await storage.approve(
        stage.id, expected_attempt_id=first.id, reviewer_user_id="u", comment="ok"
    )
    result = await build_stage_views(AsyncSessionAdapter(db), task, "function", detail=True)
    point = next(row for row in result.stages if row.stage == "case_names")
    assert (
        point.state == "approved"
        and result.draft_count == 0
        and point.latest_version.version_no == 1
    )


async def test_stage_view_exposes_failed_attempt_reason_and_time(db):  # noqa: F811
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.services.stage_storage.views import build_stage_views
    from testing_agent.services.stage_storage.worker import StageWorkerTransitions

    stage, storage = setup_stage(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == stage.task_id))
    first = await storage.prepare(
        stage.id,
        worker_task_id="first",
        requested_by="u",
        input_snapshot={"source": {}, "config": {}},
    )
    await StageWorkerTransitions(AsyncSessionAdapter(db)).failed(
        stage.id, first.id, "first", error_message="模型输出空闲超过 300 秒，执行已终止"
    )
    result = await build_stage_views(AsyncSessionAdapter(db), task, "function", detail=True)
    point = next(row for row in result.stages if row.stage == "case_names")
    assert point.state == "failed"
    assert point.error_message == "模型输出空闲超过 300 秒，执行已终止"
    assert point.failure_run_id == first.id
    assert point.failed_at is not None


async def test_version_detail_reads_frozen_source_and_allows_missing_parent(db):  # noqa: F811
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.services.stage_storage.version_views import version_detail

    stage, storage = setup_stage(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == stage.task_id))
    task.task_type = "ui_case_generate"
    stage.stage = "ui_yaml"
    source = {
        "sourceKind": "repository",
        "sourceProfileVersionId": "profile-attempt-1",
        "sourceProfileVersionNo": 1,
        "sourceRepository": {
            "repositoryId": "repo-front",
            "pathWithNamespace": "team/repo-front",
            "branch": "main",
            "commit": "sha-profile",
            "commitMode": "profile",
        },
        "functionalCases": [{"caseId": "case"}],
    }
    attempt = await storage.prepare(
        stage.id,
        worker_task_id="ui-worker",
        requested_by="u",
        input_snapshot={
            "source": source,
            "versioning": {"upstreamVersions": {"ui_surface": "missing-parent"}},
        },
    )
    await storage.publish(
        stage.id,
        attempt_id=attempt.id,
        worker_task_id="ui-worker",
        content="- name: case",
        output_format="yaml",
        output_context=None,
    )
    version = await storage.approve(
        stage.id, expected_attempt_id=attempt.id, reviewer_user_id="u", comment="ok"
    )
    detail = await version_detail(AsyncSessionAdapter(db), task, "ui", version.version_id)
    assert detail.content == "- name: case"
    assert detail.upstream_versions == {"ui_surface": "missing-parent"} and detail.upstream == []
    assert detail.source_inputs.repository.commit == "sha-profile"


async def test_ui_source_batch_survives_without_any_attempt(db):  # noqa: F811
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.services.stage_storage.chain_view import build_chain_view

    stage, _ = setup_stage(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == stage.task_id))
    task.task_type = "ui_case_generate"
    stage.stage = "ui_surface"
    stage.source_batch_id = "batch-1"
    stage.source_snapshot_json = {
        "sourceKind": "repository",
        "sourceProfileVersionId": "profile-attempt-1",
        "sourceProfileVersionNo": 1,
        "sourceRepository": {
            "repositoryId": "repo-front",
            "pathWithNamespace": "team/repo-front",
            "branch": "main",
            "commit": "sha-profile",
            "commitMode": "profile",
        },
        "functionalCases": [],
    }
    db.flush()
    view = await build_chain_view(AsyncSessionAdapter(db), "r", "ui", task, detail=True)
    assert view.source_batch_id == "batch-1"
    assert view.source_inputs.repository.commit == "sha-profile"
    assert not view.source_changed
    assert view.stages[0].state == "not_started" and view.draft_count == 0


async def test_upstream_selection_supports_latest_and_explicit_versions(db):  # noqa: F811
    from datetime import UTC, datetime

    from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.services.stage_storage.upstream import select_upstream_versions

    stage, _ = setup_stage(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == stage.task_id))
    for number in (1, 2):
        db.add(
            AiGenerateStageVersion(
                version_id=f"analysis-{number}",
                task_id=task.task_id,
                stage="requirement_analysis",
                version_no=number,
                attempt_id=f"attempt-{number}",
                artifact_content='{"name":"analysis"}',
                artifact_format="json",
                reviewer_user_id="u",
                reviewed_at=datetime.now(UTC),
                review_comment="",
                created_at=datetime.now(UTC),
            )
        )
    db.flush()
    latest = await select_upstream_versions(
        AsyncSessionAdapter(db), task, "function", "case_names", {}
    )
    assert latest["requirement_analysis"].version_id == "analysis-2"
    old = await select_upstream_versions(
        AsyncSessionAdapter(db),
        task,
        "function",
        "case_names",
        {"requirement_analysis": "analysis-1"},
    )
    assert old["requirement_analysis"].version_id == "analysis-1"
    with pytest.raises(AppError):
        await select_upstream_versions(
            AsyncSessionAdapter(db),
            task,
            "function",
            "case_names",
            {"requirement_analysis": "missing"},
        )


async def test_deleting_upstream_blocks_active_then_invalidates_only_draft(db):  # noqa: F811
    from datetime import UTC, datetime

    from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.services.stage_storage.version_delete import delete_stage_version

    stage, storage = setup_stage(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == stage.task_id))
    parent = AiGenerateStageVersion(
        version_id="parent",
        task_id=task.task_id,
        stage="requirement_analysis",
        version_no=1,
        attempt_id="old-attempt",
        artifact_content='{"analysis":1}',
        artifact_format="json",
        reviewer_user_id="u",
        reviewed_at=datetime.now(UTC),
        review_comment="",
        created_at=datetime.now(UTC),
    )
    db.add(parent)
    db.commit()
    frozen = {"versioning": {"upstreamVersions": {"requirement_analysis": "parent"}}}
    first = await storage.prepare(
        stage.id, worker_task_id="first", requested_by="u", input_snapshot=frozen
    )
    await storage.publish(
        stage.id,
        attempt_id=first.id,
        worker_task_id="first",
        content='{"old":1}',
        output_format="json",
        output_context=None,
    )
    approved = await storage.approve(
        stage.id, expected_attempt_id=first.id, reviewer_user_id="u", comment=""
    )
    second = await storage.prepare(
        stage.id, worker_task_id="second", requested_by="u", input_snapshot=frozen
    )
    with pytest.raises(AppError):
        await delete_stage_version(AsyncSessionAdapter(db), task, "parent")
    await storage.publish(
        stage.id,
        attempt_id=second.id,
        worker_task_id="second",
        content='{"draft":1}',
        output_format="json",
        output_context=None,
    )
    assert await delete_stage_version(AsyncSessionAdapter(db), task, "parent") == 1
    assert second.invalidated_at is not None and second.output_content == '{"draft":1}'
    assert first.invalidated_at is None and approved.artifact_content == '{"old":1}'
    with pytest.raises(AppError):
        await storage.approve(
            stage.id, expected_attempt_id=second.id, reviewer_user_id="u", comment=""
        )


async def test_deleting_current_approved_version_returns_candidate_to_draft(db):  # noqa: F811
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.services.stage_storage.version_delete import delete_stage_version

    stage, storage = setup_stage(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == stage.task_id))
    first = await storage.prepare(
        stage.id, worker_task_id="first", requested_by="u", input_snapshot={}
    )
    await storage.publish(
        stage.id,
        attempt_id=first.id,
        worker_task_id="first",
        content='{"approved":1}',
        output_format="json",
        output_context=None,
    )
    version = await storage.approve(
        stage.id, expected_attempt_id=first.id, reviewer_user_id="u", comment=""
    )
    assert stage.review_status == "approved"
    assert await delete_stage_version(AsyncSessionAdapter(db), task, version.version_id) == 0
    assert stage.review_status == "pending"
    draft = await storage.save_draft(
        stage.id,
        expected_attempt_id=first.id,
        requested_by="u",
        content='{"edited":2}',
        output_format="json",
    )
    assert draft.operation == "edit" and draft.output_content == '{"edited":2}'
    approved = await storage.approve(
        stage.id, expected_attempt_id=draft.id, reviewer_user_id="u", comment=""
    )
    assert approved.version_no == 2


async def test_cross_chain_requirement_version_delete_preserves_approved_function_version(db):  # noqa: F811
    from datetime import UTC, datetime

    from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.services.stage_storage.version_delete import delete_stage_version

    stage, storage = setup_stage(db)
    source_task = AiGenerateTask(
        task_id="analysis-task",
        task_type="requirement_analysis",
        name="需求分析",
        project_id="p",
        sprint_id="s",
        requirement_id="r",
        creator_user_id="u",
        source_type="text",
        source_content="",
        instruction="",
    )
    db.add(source_task)
    db.flush()
    version = AiGenerateStageVersion(
        version_id="understanding",
        task_id=source_task.task_id,
        stage="feature_understanding",
        version_no=1,
        attempt_id="old-attempt",
        artifact_content='{"name":"requirement"}',
        artifact_format="json",
        reviewer_user_id="u",
        reviewed_at=datetime.now(UTC),
        review_comment="",
        created_at=datetime.now(UTC),
    )
    db.add(version)
    db.commit()
    frozen = {"source": {"requirementUnderstandingVersion": {"versionId": "understanding"}}}
    first = await storage.prepare(
        stage.id, worker_task_id="first", requested_by="u", input_snapshot=frozen
    )
    await storage.publish(
        stage.id,
        attempt_id=first.id,
        worker_task_id="first",
        content='{"old":1}',
        output_format="json",
        output_context=None,
    )
    approved = await storage.approve(
        stage.id, expected_attempt_id=first.id, reviewer_user_id="u", comment=""
    )
    second = await storage.prepare(
        stage.id, worker_task_id="second", requested_by="u", input_snapshot=frozen
    )
    await storage.publish(
        stage.id,
        attempt_id=second.id,
        worker_task_id="second",
        content='{"draft":1}',
        output_format="json",
        output_context=None,
    )
    assert await delete_stage_version(AsyncSessionAdapter(db), source_task, "understanding") == 1
    assert second.invalidated_at is not None
    assert first.invalidated_at is None and approved.artifact_content == '{"old":1}'


async def test_failed_rerun_never_makes_approved_candidate_editable(db):  # noqa: F811
    from testing_agent.services.stage_storage.worker import StageWorkerTransitions

    stage, storage = setup_stage(db)
    first = await storage.prepare(
        stage.id, worker_task_id="first", requested_by="u", input_snapshot={}
    )
    await storage.publish(
        stage.id,
        attempt_id=first.id,
        worker_task_id="first",
        content='{"approved":1}',
        output_format="json",
        output_context=None,
    )
    await storage.approve(stage.id, expected_attempt_id=first.id, reviewer_user_id="u", comment="")
    second = await storage.prepare(
        stage.id, worker_task_id="second", requested_by="u", input_snapshot={}
    )
    await StageWorkerTransitions(AsyncSessionAdapter(db)).failed(
        stage.id, second.id, "second", error_message="失败"
    )
    with pytest.raises(AppError):
        await storage.save_draft(
            stage.id,
            expected_attempt_id=first.id,
            requested_by="u",
            content='{"mutated":1}',
            output_format="json",
        )
    with pytest.raises(AppError):
        await storage.reject(stage.id, expected_attempt_id=first.id)
    with pytest.raises(AppError):
        await storage.approve(
            stage.id, expected_attempt_id=first.id, reviewer_user_id="u", comment="again"
        )
    retry = await storage.prepare(
        stage.id, worker_task_id="retry", requested_by="u", input_snapshot={}
    )
    assert retry.id != first.id


async def test_direct_commands_validate_save_and_review_candidate(db):  # noqa: F811
    from support.generation import generation_services

    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.schemas.generation_chain import (
        GenerationChainReviewRequest,
        GenerationChainSaveDraftRequest,
    )
    from testing_agent.services.stage_storage.commands import DirectStageCommands

    stage, storage = setup_stage(db)
    attempt = await storage.prepare(
        stage.id, worker_task_id="first", requested_by="u", input_snapshot={"source": {}}
    )
    await storage.publish(
        stage.id,
        attempt_id=attempt.id,
        worker_task_id="first",
        content='{"x":1}',
        output_format="json",
        output_context=None,
    )
    db.commit()
    commands = DirectStageCommands(
        generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(db))).chain
    )
    with pytest.raises(AppError):
        await commands.save(
            "r",
            "function",
            "case_names",
            GenerationChainSaveDraftRequest(expectedAttemptId=attempt.id, content="not-json"),
            "u",
        )
    saved = await commands.save(
        "r",
        "function",
        "case_names",
        GenerationChainSaveDraftRequest(expectedAttemptId=attempt.id, content='{"point":2}'),
        "u",
    )
    point = next(item for item in saved.stages if item.stage == "case_names")
    assert point.draft.content == '{"point": 2}'
    with pytest.raises(AppError):
        await commands.review(
            "r",
            "function",
            "case_names",
            GenerationChainReviewRequest(action="approve", expectedAttemptId=attempt.id),
            "u",
        )
    result = await commands.review(
        "r",
        "function",
        "case_names",
        GenerationChainReviewRequest(action="approve", expectedAttemptId=point.draft.attempt_id),
        "u",
    )
    assert next(item for item in result.stages if item.stage == "case_names").state == "approved"
    again = await commands.review(
        "r",
        "function",
        "case_names",
        GenerationChainReviewRequest(action="approve", expectedAttemptId=point.draft.attempt_id),
        "u",
    )
    assert again.stages[1].latest_version.version_id == result.stages[1].latest_version.version_id
    with pytest.raises(AppError, match="不能重新驳回"):
        await commands.review(
            "r",
            "function",
            "case_names",
            GenerationChainReviewRequest(action="reject", expectedAttemptId=point.draft.attempt_id),
            "u",
        )


async def test_direct_revision_keeps_frozen_input_and_is_idempotent(db, monkeypatch):  # noqa: F811
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from support.generation import generation_services

    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.schemas.generation_chain import GenerationChainRevisionRequest
    from testing_agent.services.stage_storage import commands as commands_module

    stage, storage = setup_stage(db)
    original = await storage.prepare(
        stage.id,
        worker_task_id="old-worker",
        requested_by="u",
        input_snapshot={"source": {"sourceContent": "frozen"}, "config": {}},
    )
    await storage.publish(
        stage.id,
        attempt_id=original.id,
        worker_task_id="old-worker",
        content='{"point": 1}',
        output_format="json",
        output_context=None,
    )
    db.commit()
    chain = generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(db))).chain
    monkeypatch.setattr(commands_module, "require_personal_connection", AsyncMock())
    commands = commands_module.DirectStageCommands(chain)
    body = GenerationChainRevisionRequest(connectionId="llm", instruction="补充", requestId=uuid4())
    await commands.revise("r", "function", "case_names", body, "u")
    await commands.revise("r", "function", "case_names", body, "u")
    for changed in (
        body.model_copy(update={"connection_id": "other"}),
        body.model_copy(update={"instruction": "不同内容"}),
        body.model_copy(update={"attachment_file_ids": ["different-file"]}),
    ):
        with pytest.raises(AppError):
            await commands.revise("r", "function", "case_names", changed, "u")
    attempts = db.scalars(
        select(AiGenerationAttempt).where(AiGenerationAttempt.operation == "revise")
    ).all()
    assert len(attempts) == 1
    assert attempts[0].input_snapshot_json["source"]["sourceContent"] == "frozen"
    assert attempts[0].input_snapshot_json["config"]["caseNames"] == {"point": 1}
    revised = attempts[0]
    await storage.publish(
        stage.id,
        attempt_id=revised.id,
        worker_task_id=str(body.request_id),
        content='{"point":2}',
        output_format="json",
        output_context=None,
    )
    await storage.reject(stage.id, expected_attempt_id=revised.id)
    db.commit()
    assert set(revised.input_snapshot_json) == {"requestSignature"}
    await commands.revise("r", "function", "case_names", body, "u")


async def test_import_approved_direct_function_without_upstream_history(db):  # noqa: F811
    from support.generation import generation_services

    from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
    from testing_agent.models.function_test_case import FunctionTestCase
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.schemas.generation_chain import GenerationChainImportRequest

    stage, storage = setup_stage(db)
    stage.stage = "detailed_cases"
    attempt = await storage.prepare(
        stage.id, worker_task_id="direct-worker", requested_by="u", input_snapshot={"source": {}}
    )
    await storage.publish(
        stage.id,
        attempt_id=attempt.id,
        worker_task_id="direct-worker",
        output_format="yaml",
        content="""cases:
  - module: 登录
    title: 登录成功
    preconditions: 已注册账号
    steps: 输入正确账号密码
    expected_results: 进入首页
    priority: P0
    case_type: smoke
""",
        output_context=None,
    )
    version = await storage.approve(
        stage.id, expected_attempt_id=attempt.id, reviewer_user_id="u", comment=""
    )
    db.commit()
    chain = generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(db))).chain
    result = await chain.import_version(
        "r",
        "function",
        version.version_id,
        GenerationChainImportRequest(confirmOverwrite=True),
        "u",
    )
    assert result.imported
    assert db.scalar(select(FunctionTestCase)).title == "登录成功"
    assert db.scalar(select(AiGenerateVersionImport)).parent_versions_json is None


async def test_rejection_removes_candidate_and_unshared_queue_error(db):  # noqa: F811
    from testing_agent.models.worker_task import WorkerTask

    stage, storage = setup_stage(db)
    attempt = await storage.prepare(
        stage.id,
        worker_task_id="worker",
        requested_by="u",
        input_snapshot={"source": {"private": "discard"}},
    )
    db.add(
        WorkerTask(
            domain="ai",
            task_id="worker",
            task_type="functional_case_generate",
            run_id=attempt.id,
            status="success",
            error_message="discard error",
        )
    )
    await storage.publish(
        stage.id,
        attempt_id=attempt.id,
        worker_task_id="worker",
        content='{"private":"discard"}',
        output_format="json",
        output_context={"private": "discard"},
    )
    await storage.reject(stage.id, expected_attempt_id=attempt.id)
    db.expire_all()
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "worker"))
    stored = db.get(type(attempt), attempt.id)
    assert stored.output_content is None and stored.input_snapshot_json is None
    assert stored.output_context_json is None and queue.error_message == ""


async def test_function_two_stage_flow_does_not_create_old_run(db, monkeypatch):  # noqa: F811
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from support.generation import generation_services
    from support.requirement_versions import understanding_version

    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.repositories.worker_task import WorkerTaskRepository
    from testing_agent.schemas.generation_chain import (
        GenerationChainReviewRequest,
        GenerationChainRunRequest,
    )
    from testing_agent.schemas.workers import (
        WorkerClaimRequest,
        WorkerProgressRequest,
        WorkerTaskEventRequest,
    )
    from testing_agent.services.stage_storage import authorization, run_command
    from testing_agent.services.stage_storage.commands import DirectStageCommands
    from testing_agent.services.worker_task import WorkerTaskService

    stage, _ = setup_stage(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == stage.task_id))
    understanding = understanding_version(db)
    adapter = AsyncSessionAdapter(db)
    bundle = generation_services(AiGenerateTaskRepository(adapter))
    connection_check = AsyncMock()
    monkeypatch.setattr(run_command, "require_personal_connection", connection_check)
    monkeypatch.setattr(authorization, "require_project_id", AsyncMock())
    monkeypatch.setattr(authorization, "require_personal_connection", AsyncMock())
    request_id = uuid4()
    body = GenerationChainRunRequest(connectionId="llm", requestId=request_id)
    attempt = await run_command.start_stage(
        bundle.chain, task, "function", "requirement_analysis", body, "u"
    )
    assert attempt.input_snapshot_json["versioning"]["upstreamVersions"] == {
        "feature_understanding": understanding.version_id
    }
    await adapter.commit()
    same = await run_command.start_stage(
        bundle.chain, task, "function", "requirement_analysis", body, "u"
    )
    assert same.id == attempt.id
    from testing_agent.core.errors import ErrForbidden

    connection_check.side_effect = ErrForbidden()
    with pytest.raises(AppError) as revoked:
        await run_command.start_stage(
            bundle.chain, task, "function", "requirement_analysis", body, "u"
        )
    assert revoked.value.http_code == 403
    connection_check.side_effect = None
    for changed in (
        body.model_copy(update={"connection_id": "other"}),
        body.model_copy(update={"instruction": "different"}),
        body.model_copy(update={"config_json": {"custom": "different"}}),
        body.model_copy(update={"upstream_versions": {"feature_understanding": "different"}}),
    ):
        with pytest.raises(AppError):
            await run_command.start_stage(
                bundle.chain, task, "function", "requirement_analysis", changed, "u"
            )
    worker = WorkerTaskService(WorkerTaskRepository(adapter))
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == str(request_id)))
    await worker._claim_task("ai", queue, WorkerClaimRequest(worker_id="node"))
    await worker.started("ai", queue.task_id, WorkerTaskEventRequest(worker_id="node"))
    await worker.progress(
        queue.task_id,
        WorkerProgressRequest(
            worker_id="node",
            current_stage="requirement_analysis",
            stage_status="waiting_review",
            config_json={"requirementAnalysis": {"purpose": "login"}},
        ),
    )
    await DirectStageCommands(bundle.chain).review(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainReviewRequest(action="approve", expectedAttemptId=attempt.id),
        "u",
    )
    second = await run_command.start_stage(
        bundle.chain,
        task,
        "function",
        "case_names",
        GenerationChainRunRequest(connectionId="llm"),
        "u",
    )
    assert second.input_snapshot_json["config"]["requirementAnalysis"] == {"purpose": "login"}
    assert second.input_snapshot_json["source"]["sourceContent"] == "versioned source"


async def test_approval_remains_if_next_dispatch_fails(db, monkeypatch):  # noqa: F811
    from unittest.mock import AsyncMock

    from support.generation import generation_services

    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.schemas.generation_chain import GenerationChainReviewRequest
    from testing_agent.services.stage_storage import run_command
    from testing_agent.services.stage_storage.commands import DirectStageCommands

    stage, storage = setup_stage(db)
    attempt = await storage.prepare(
        stage.id,
        worker_task_id="first",
        requested_by="u",
        input_snapshot={"source": {}, "llmConnectionId": "llm"},
    )
    await storage.publish(
        stage.id,
        attempt_id=attempt.id,
        worker_task_id="first",
        content='{"point":1}',
        output_format="json",
        output_context=None,
    )
    db.commit()
    monkeypatch.setattr(run_command, "require_personal_connection", AsyncMock())
    commands = DirectStageCommands(
        generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(db))).chain
    )
    result = await commands.review(
        "r",
        "function",
        "case_names",
        GenerationChainReviewRequest(
            action="approve", expectedAttemptId=attempt.id, continueAfter=True, connectionId="llm"
        ),
        "u",
    )
    point = next(item for item in result.stages if item.stage == "case_names")
    assert point.state == "approved" and point.latest_version is not None
    assert "测试需求分析" in result.continuation_error


async def test_approval_can_continue_to_next_direct_stage(db, monkeypatch):  # noqa: F811
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from support.generation import generation_services
    from support.requirement_versions import understanding_version

    from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.schemas.generation_chain import GenerationChainReviewRequest
    from testing_agent.services.stage_storage import commands as command_module
    from testing_agent.services.stage_storage import run_command
    from testing_agent.services.stage_storage.commands import DirectStageCommands

    stage, storage = setup_stage(db)
    understanding_version(db)
    db.add(
        AiGenerateStageVersion(
            version_id="analysis",
            task_id="task",
            stage="requirement_analysis",
            version_no=1,
            attempt_id="old",
            artifact_content='{"purpose":"login"}',
            artifact_format="json",
            reviewer_user_id="u",
            reviewed_at=datetime.now(UTC),
            review_comment="",
            created_at=datetime.now(UTC),
        )
    )
    db.commit()
    attempt = await storage.prepare(
        stage.id,
        worker_task_id="first",
        requested_by="u",
        input_snapshot={
            "source": {},
            "llmConnectionId": "llm",
            "versioning": {"upstreamVersions": {"requirement_analysis": "analysis"}},
        },
    )
    await storage.publish(
        stage.id,
        attempt_id=attempt.id,
        worker_task_id="first",
        content='{"point":1}',
        output_format="json",
        output_context=None,
    )
    db.commit()
    monkeypatch.setattr(run_command, "require_personal_connection", AsyncMock())
    commands = DirectStageCommands(
        generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(db))).chain
    )
    request = GenerationChainReviewRequest(
        action="approve",
        expectedAttemptId=attempt.id,
        continueAfter=True,
        connectionId="llm",
        requestId=uuid4(),
    )
    real_start = command_module.start_stage
    monkeypatch.setattr(command_module, "start_stage", AsyncMock(side_effect=AppError(400, "失败")))
    failed = await commands.review("r", "function", "case_names", request, "u")
    assert failed.continuation_error
    monkeypatch.setattr(command_module, "start_stage", real_start)
    result = await commands.review(
        "r",
        "function",
        "case_names",
        request,
        "u",
    )
    assert result.continuation_error == ""
    assert next(item for item in result.stages if item.stage == "case_names").state == "approved"
    assert next(item for item in result.stages if item.stage == "detailed_cases").state == "running"
    from testing_agent.models.worker_task import WorkerTask

    replay = await commands.review("r", "function", "case_names", request, "u")
    assert replay.continuation_error == ""
    matching = db.scalars(select(WorkerTask).where(WorkerTask.task_id == str(request.request_id)))
    assert len(matching.all()) == 1
    with pytest.raises(AppError):
        await commands.review(
            "r",
            "function",
            "case_names",
            request.model_copy(update={"instruction": "changed"}),
            "u",
        )


async def test_ui_refresh_changes_batch_and_rejects_old_late_worker(db, monkeypatch):  # noqa: F811
    from unittest.mock import AsyncMock

    from support.generation import generation_services

    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.schemas.generation_chain import GenerationChainRunRequest
    from testing_agent.services.stage_storage import run_command
    from testing_agent.services.stage_storage.worker import StageWorkerTransitions
    from testing_agent.services.ui_generation_source import ResolvedUiSource

    stage, _ = setup_stage(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == stage.task_id))
    task.task_type = "ui_case_generate"
    stage.stage = "ui_surface"

    def resolved(commit: str) -> ResolvedUiSource:
        return ResolvedUiSource(
            profile_version_id="profile-attempt-1",
            profile_version_no=1,
            repository={
                "bindingId": "binding-1",
                "repositoryId": "repo-front",
                "instanceUrl": "https://gitlab.example.com",
                "pathWithNamespace": "team/repo-front",
                "branch": "main",
                "commit": commit,
                "commitMode": "profile",
                "resolvedAt": "2026-11-09T00:00:00+00:00",
            },
            binding={
                "bindingId": "binding-1",
                "repositoryId": "repo-front",
                "instanceUrl": "https://gitlab.example.com",
                "pathWithNamespace": "team/repo-front",
                "branch": "main",
                "headCommit": commit,
                "cloneUrl": "https://gitlab.example.com/team/repo-front.git",
                "connectionId": "ui-conn",
                "profileError": "",
            },
        )

    db.commit()
    adapter = AsyncSessionAdapter(db)
    bundle = generation_services(AiGenerateTaskRepository(adapter))
    bundle.chain.ui_sources.resolve = AsyncMock(return_value=resolved("sha-one"))
    monkeypatch.setattr(run_command, "require_personal_connection", AsyncMock())
    monkeypatch.setattr(
        bundle.chain.tasks, "list_ui_source_cases", AsyncMock(return_value=[{"caseId": "case-1"}])
    )
    body = GenerationChainRunRequest(
        connectionId="llm",
        functionCaseIds=["case-1"],
        sourceProfileVersionId="profile-attempt-1",
        sourceRepositoryId="repo-front",
    )
    first = await run_command.start_stage(bundle.chain, task, "ui", "ui_surface", body, "u")
    old_batch = stage.source_batch_id
    with pytest.raises(AppError):
        await run_command.start_stage(
            bundle.chain,
            task,
            "ui",
            "ui_surface",
            GenerationChainRunRequest(
                connectionId="llm",
                refreshInputs=True,
                functionCaseIds=["case-1"],
                sourceProfileVersionId="profile-attempt-1",
                sourceRepositoryId="repo-front",
            ),
            "u",
        )
    assert stage.source_batch_id == old_batch
    assert stage.active_attempt_id == first.id
    storage = DirectStageStorage(adapter)
    await storage.publish(
        stage.id,
        attempt_id=first.id,
        worker_task_id=first.worker_task_id,
        content='{"page":"one"}',
        output_format="json",
        output_context=None,
    )
    db.scalar(
        select(WorkerTask).where(WorkerTask.task_id == first.worker_task_id)
    ).status = "success"
    approved = await storage.approve(
        stage.id, expected_attempt_id=first.id, reviewer_user_id="u", comment=""
    )
    design = await run_command.start_stage(
        bundle.chain, task, "ui", "ui_design", GenerationChainRunRequest(connectionId="llm"), "u"
    )
    old_queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == design.worker_task_id))
    bundle.chain.ui_sources.resolve = AsyncMock(return_value=resolved("sha-two"))
    db.commit()
    with monkeypatch.context() as patcher:
        patcher.setattr(
            run_command,
            "dispatch_stage_attempt",
            AsyncMock(side_effect=RuntimeError("queue failed")),
        )
        with pytest.raises(RuntimeError, match="queue failed"):
            await run_command.start_stage(
                bundle.chain,
                task,
                "ui",
                "ui_surface",
                GenerationChainRunRequest(
                    connectionId="llm",
                    refreshInputs=True,
                    functionCaseIds=["case-1"],
                    sourceProfileVersionId="profile-attempt-1",
                    sourceRepositoryId="repo-front",
                ),
                "u",
            )
        db.rollback()
    db.expire_all()
    assert stage.source_batch_id == old_batch
    assert design.status == "pending" and old_queue.status == "pending"
    assert approved.artifact_content == '{"page":"one"}'
    refreshed = await run_command.start_stage(
        bundle.chain,
        task,
        "ui",
        "ui_surface",
        GenerationChainRunRequest(
            connectionId="llm",
            refreshInputs=True,
            functionCaseIds=["case-1"],
            sourceProfileVersionId="profile-attempt-1",
            sourceRepositoryId="repo-front",
        ),
        "u",
    )
    assert (
        stage.source_batch_id != old_batch
        and stage.source_snapshot_json["sourceRepository"]["commit"] == "sha-two"
    )
    assert design.status == "canceled" and old_queue.status == "canceled"
    assert approved.artifact_content == '{"page":"one"}' and refreshed.status == "pending"
    with pytest.raises(AppError):
        await StageWorkerTransitions(adapter).completed(
            design.stage_id,
            design.id,
            design.worker_task_id,
            content='{"stale":1}',
            output_format="json",
            output_context=None,
        )


async def test_graph_result_is_bound_to_approved_case_version(db, monkeypatch):  # noqa: F811
    from unittest.mock import AsyncMock

    from support.direct_graph import cases_output, relations_output

    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.schemas.ai_generate_task import AiGenerateTaskRunResponse
    from testing_agent.schemas.workers import WorkerTaskEventRequest
    from testing_agent.services.stage_storage import relations
    from testing_agent.services.stage_storage.version_delete import delete_stage_version
    from testing_agent.services.stage_storage.worker_events import apply_stage_completion

    stage, storage = setup_stage(db)
    stage.stage = "detailed_cases"
    first = await storage.prepare(
        stage.id,
        worker_task_id="leaf",
        requested_by="u",
        input_snapshot={
            "source": {"sourceContent": "source"},
            "config": {"requirementAnalysis": {"purpose": "login"}},
        },
    )
    await storage.publish(
        stage.id,
        attempt_id=first.id,
        worker_task_id="leaf",
        content=cases_output(),
        output_format="json",
        output_context=None,
    )
    version = await storage.approve(
        stage.id, expected_attempt_id=first.id, reviewer_user_id="u", comment=""
    )
    db.commit()
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    monkeypatch.setattr(relations, "require_personal_connection", AsyncMock())
    graph = await relations.launch_graph(AsyncSessionAdapter(db), task, first.id, "u", "llm")
    with pytest.raises(AppError):
        await delete_stage_version(AsyncSessionAdapter(db), task, version.version_id)
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == graph.worker_task_id))
    await apply_stage_completion(
        AsyncSessionAdapter(db),
        queue,
        stage_id=graph.stage_id,
        attempt_id=graph.id,
        kind="function",
        stage="relation_analysis",
        source=graph.input_snapshot_json["source"],
        frozen_config=graph.input_snapshot_json["config"],
        body=WorkerTaskEventRequest(
            worker_id="worker",
            status="success",
            config_json={
                "requirementAnalysis": {"purpose": "login"},
                "caseNames": None,
                "caseRelations": relations_output(),
            },
        ),
    )
    assert (
        await relations.graph_for_version(AsyncSessionAdapter(db), task, version)
    ).id == graph.id
    response = AiGenerateTaskRunResponse.model_validate(
        await relations.graph_view(AsyncSessionAdapter(db), task, first)
    )
    assert response.config_json["caseRelations"] == relations_output()
    assert db.get(AiGenerationStage, graph.stage_id).review_status == "not_required"
    assert first.output_content == cases_output()


@pytest.mark.parametrize("kind", ["api", "ui"])
async def test_direct_api_and_ui_import_without_old_run(db, kind):  # noqa: F811
    from support.generation import generation_services
    from support.ui_import_fixtures import approved_ui_run

    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
    from testing_agent.models.api_case import ApiCase
    from testing_agent.models.api_collection import ApiCollection
    from testing_agent.models.ui_test_case import UiTestCase
    from testing_agent.models.ui_test_suite import UiTestSuite
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.schemas.generation_chain import GenerationChainImportRequest

    stage, storage = setup_stage(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.task_type = "api_case_generate" if kind == "api" else "ui_case_generate"
    stage.stage = "generate" if kind == "api" else "ui_yaml"
    if kind == "api":
        db.add(ApiCollection(collection_id="target", requirement_id="r", name="target"))
        content = "cases:\n  - name: Login\n    method: GET\n    urlTemplate: /login\n"
    else:
        db.add(UiTestSuite(suite_id="target", requirement_id="r", name="target"))
        content = approved_ui_run().result_yaml
    attempt = await storage.prepare(
        stage.id, worker_task_id="leaf", requested_by="u", input_snapshot={"source": {}}
    )
    await storage.publish(
        stage.id,
        attempt_id=attempt.id,
        worker_task_id="leaf",
        content=content,
        output_format="yaml",
        output_context=None,
    )
    version = await storage.approve(
        stage.id, expected_attempt_id=attempt.id, reviewer_user_id="u", comment=""
    )
    db.commit()
    chain = generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(db))).chain
    result = await chain.import_version(
        "r",
        kind,
        version.version_id,
        GenerationChainImportRequest(targetId="target", confirmOverwrite=True),
        "u",
    )
    assert result.imported
    assert db.scalar(select(ApiCase if kind == "api" else UiTestCase)) is not None
    assert db.scalar(select(AiGenerateVersionImport)).version_id == version.version_id


async def test_stage_http_edit_and_review_use_direct_attempt(db):  # noqa: F811
    import httpx
    from support.generation import generation_services, install_generation_services

    from testing_agent.api.deps import get_current_user_id
    from testing_agent.app import create_app
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository

    stage, storage = setup_stage(db)
    candidate = await storage.prepare(
        stage.id, worker_task_id="worker", requested_by="u", input_snapshot={"source": {}}
    )
    await storage.publish(
        stage.id,
        attempt_id=candidate.id,
        worker_task_id="worker",
        content='{"point": 1}',
        output_format="json",
        output_context=None,
    )
    db.commit()
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "u"
    install_generation_services(
        app, generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(db)))
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        overview = await client.get("/v1/requirements/r/generation")
        assert overview.status_code == 200, overview.text
        detail = await client.get("/v1/requirements/r/generation/function")
        assert detail.status_code == 200, detail.text
        saved = await client.put(
            "/v1/requirements/r/generation/function/stages/case_names/draft",
            json={"expectedAttemptId": candidate.id, "content": '{"point": 2}'},
        )
        assert saved.status_code == 200, saved.text
        point = next(
            item for item in saved.json()["data"]["stages"] if item["stage"] == "case_names"
        )
        approved = await client.post(
            "/v1/requirements/r/generation/function/stages/case_names/review",
            json={"action": "approve", "expectedAttemptId": point["draft"]["attemptId"]},
        )
        assert approved.status_code == 200, approved.text
        point = next(
            item for item in approved.json()["data"]["stages"] if item["stage"] == "case_names"
        )
        assert point["state"] == "approved"


async def test_direct_revision_attachment_owner_requires_frozen_file_reference(db):  # noqa: F811
    from types import SimpleNamespace

    from testing_agent.services.stored_file_access import require_file_resource

    stage, storage = setup_stage(db)
    attempt = await storage.prepare(
        stage.id,
        worker_task_id="worker",
        requested_by="u",
        input_snapshot={"config": {"revisionAttachments": [{"fileId": "file"}]}},
    )
    row = SimpleNamespace(
        status="attached",
        resource_id=attempt.id,
        resource_type="ai_generate_run",
        project_id="p",
        purpose="attachment",
        file_id="file",
    )
    await require_file_resource(AsyncSessionAdapter(db), row)
    row.file_id = "other"
    with pytest.raises(AppError):
        await require_file_resource(AsyncSessionAdapter(db), row)


async def test_graph_http_uses_version_attempt_identity(db, monkeypatch):  # noqa: F811
    from unittest.mock import AsyncMock

    import httpx
    from support.direct_graph import cases_output
    from support.generation import generation_services, install_generation_services

    from testing_agent.api.deps import get_current_user_id
    from testing_agent.app import create_app
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.services.stage_storage import relations

    stage, storage = setup_stage(db)
    stage.stage = "detailed_cases"
    leaf = await storage.prepare(
        stage.id,
        worker_task_id="leaf",
        requested_by="u",
        input_snapshot={
            "source": {"sourceContent": "source"},
            "config": {"requirementAnalysis": {"purpose": "login"}},
            "llmConnectionId": "llm",
        },
    )
    await storage.publish(
        stage.id,
        attempt_id=leaf.id,
        worker_task_id="leaf",
        content=cases_output(),
        output_format="json",
        output_context=None,
    )
    await storage.approve(stage.id, expected_attempt_id=leaf.id, reviewer_user_id="u", comment="")
    db.commit()
    monkeypatch.setattr(relations, "require_personal_connection", AsyncMock())
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "u"
    install_generation_services(
        app, generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(db)))
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        url = f"/v1/function-case-generate-task-runs/{leaf.id}"
        ready = await client.get(url)
        assert ready.status_code == 200, ready.text
        assert ready.json()["data"]["reviewStatus"] == "approved"
        started = await client.post(url + "/relation-analysis", json={"connectionId": "llm"})
        assert started.status_code == 200, started.text
        assert started.json()["data"]["currentStage"] == "relation_analysis"
        repeated = await client.post(url + "/relation-analysis", json={"connectionId": "llm"})
        assert repeated.status_code == 400


async def test_graph_without_explicit_version_is_not_assigned(db):  # noqa: F811
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.services.stage_storage.relations import graph_for_version

    stage, storage = setup_stage(db)
    stage.stage = "detailed_cases"
    versions = []
    for idx in range(2):
        attempt = await storage.prepare(
            stage.id, worker_task_id=f"leaf-{idx}", requested_by="u", input_snapshot={}
        )
        await storage.publish(
            stage.id,
            attempt_id=attempt.id,
            worker_task_id=f"leaf-{idx}",
            content=f"v{idx}",
            output_format="text",
            output_context=None,
        )
        version = await storage.approve(
            stage.id, expected_attempt_id=attempt.id, reviewer_user_id="u", comment=""
        )
        versions.append(version)
    graph_stage = AiGenerationStage(
        id="graph-stage", task_id="task", stage="relation_analysis", next_version_no=1
    )
    db.add(graph_stage)
    db.flush()
    db.add(
        AiGenerationAttempt(
            id="old-graph",
            stage_id=graph_stage.id,
            attempt_no=1,
            operation="generate",
            status="success",
            output_content="{}",
            invalidated_reason="",
        )
    )
    db.flush()
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    assert await graph_for_version(AsyncSessionAdapter(db), task, versions[0]) is None
    assert await graph_for_version(AsyncSessionAdapter(db), task, versions[1]) is None


async def test_direct_ui_three_stages_keep_frozen_inputs(db, monkeypatch):  # noqa: F811
    import json
    from unittest.mock import AsyncMock

    from support.generation import generation_services
    from support.ui_generation_fixtures import FIXTURES, read

    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.models.function_test_case import FunctionTestCase
    from testing_agent.models.function_test_suite import FunctionTestSuite
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.schemas.generation_chain import (
        GenerationChainReviewRequest,
        GenerationChainRunRequest,
        GenerationChainSaveDraftRequest,
    )
    from testing_agent.schemas.workers import WorkerProgressRequest, WorkerTaskEventRequest
    from testing_agent.services.stage_storage import run_command
    from testing_agent.services.stage_storage.commands import DirectStageCommands
    from testing_agent.services.stage_storage.worker_events import (
        apply_stage_completion,
        apply_stage_progress,
    )
    from testing_agent.services.ui_generation_source import ResolvedUiSource

    stage, _ = setup_stage(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.task_type, task.source_type, stage.stage = (
        "ui_case_generate",
        "repository",
        "ui_surface",
    )
    db.add(FunctionTestSuite(suite_id="suite", requirement_id="r", name="功能"))
    db.flush()
    db.add(
        FunctionTestCase(
            case_id="C1",
            suite_id="suite",
            title="显示记录名称",
            content=read("cases")[0]["content"],
        )
    )
    db.commit()
    monkeypatch.setattr(run_command, "require_personal_connection", AsyncMock())
    session = AsyncSessionAdapter(db)
    chain = generation_services(AiGenerateTaskRepository(session)).chain
    chain.ui_sources.resolve = AsyncMock(
        return_value=ResolvedUiSource(
            profile_version_id="profile-attempt-1",
            profile_version_no=1,
            repository={
                "bindingId": "binding-1",
                "repositoryId": "repo-front",
                "instanceUrl": "https://gitlab.example.com",
                "pathWithNamespace": "team/repo-front",
                "branch": "main",
                "commit": "sha-profile",
                "commitMode": "profile",
                "resolvedAt": "2026-11-09T00:00:00+00:00",
            },
            binding={
                "bindingId": "binding-1",
                "repositoryId": "repo-front",
                "instanceUrl": "https://gitlab.example.com",
                "pathWithNamespace": "team/repo-front",
                "branch": "main",
                "headCommit": "sha-profile",
                "cloneUrl": "https://gitlab.example.com/team/repo-front.git",
                "connectionId": "ui-conn",
                "profileError": "",
            },
        )
    )
    commands = DirectStageCommands(chain)
    for name, field, fixture in (
        ("ui_surface", "uiSurface", "surface"),
        ("ui_design", "uiDesign", "design"),
    ):
        run_body = GenerationChainRunRequest(
            connectionId="llm",
            sourceProfileVersionId="profile-attempt-1",
            sourceRepositoryId="repo-front",
        )
        if name != "ui_surface":
            run_body = GenerationChainRunRequest(connectionId="llm")
        await commands.run("r", "ui", name, run_body, "u")
        row = db.scalar(
            select(AiGenerationStage).where(
                AiGenerationStage.task_id == "task", AiGenerationStage.stage == name
            )
        )
        attempt = db.get(
            AiGenerationAttempt,
            row.active_attempt_id,
        )
        queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == attempt.worker_task_id))
        frozen = attempt.input_snapshot_json
        await apply_stage_progress(
            session,
            queue,
            stage_id=row.id,
            attempt_id=attempt.id,
            kind="ui",
            stage=name,
            source=frozen["source"],
            frozen_config=frozen["config"],
            body=WorkerProgressRequest(
                worker_id="worker",
                current_stage=name,
                stage_status="waiting_review",
                config_json={**frozen["config"], field: read(fixture)},
            ),
        )
        if name == "ui_surface":
            edited = read("surface")
            edited["pages"][0]["title"] = "编辑后的记录"
            saved = await commands.save(
                "r",
                "ui",
                name,
                GenerationChainSaveDraftRequest(
                    expectedAttemptId=attempt.id, content=json.dumps(edited, ensure_ascii=False)
                ),
                "u",
            )
            attempt = db.get(AiGenerationAttempt, saved.stages[0].draft.attempt_id)
            assert json.loads(attempt.output_content)["pages"][0]["title"] == "编辑后的记录"
        reviewed = await commands.review(
            "r",
            "ui",
            name,
            GenerationChainReviewRequest(action="approve", expectedAttemptId=attempt.id),
            "u",
        )
        assert not reviewed.busy
    await commands.run("r", "ui", "ui_yaml", GenerationChainRunRequest(connectionId="llm"), "u")
    row = db.scalar(
        select(AiGenerationStage).where(
            AiGenerationStage.task_id == "task", AiGenerationStage.stage == "ui_yaml"
        )
    )
    attempt = db.get(
        AiGenerationAttempt,
        row.active_attempt_id,
    )
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == attempt.worker_task_id))
    frozen = attempt.input_snapshot_json
    assert frozen["source"]["functionalCases"][0]["caseId"] == "C1"
    await apply_stage_completion(
        session,
        queue,
        stage_id=row.id,
        attempt_id=attempt.id,
        kind="ui",
        stage="ui_yaml",
        source=frozen["source"],
        frozen_config=frozen["config"],
        body=WorkerTaskEventRequest(
            worker_id="worker",
            status="success",
            config_json=frozen["config"],
            output_yaml=(FIXTURES / "draft.yaml").read_text(),
        ),
    )
    result = await commands.review(
        "r",
        "ui",
        "ui_yaml",
        GenerationChainReviewRequest(action="approve", expectedAttemptId=attempt.id),
        "u",
    )
    assert result.stages[-1].state == "approved"


async def test_ui_version_must_use_current_leaf_stage(db):  # noqa: F811
    from support.generation import generation_services
    from support.ui_import_fixtures import approved_ui_run

    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.ui_test_suite import UiTestSuite
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.services.stage_storage.chain_view import build_chain_view
    from testing_agent.services.stage_storage.version_views import version_detail

    stage, storage = setup_stage(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.task_type = "ui_case_generate"
    stage.stage = "generate"
    db.add(UiTestSuite(suite_id="target", requirement_id="r", name="UI"))
    attempt = await storage.prepare(
        stage.id, worker_task_id="legacy", requested_by="u", input_snapshot={"source": {}}
    )
    await storage.publish(
        stage.id,
        attempt_id=attempt.id,
        worker_task_id="legacy",
        content=approved_ui_run().result_yaml,
        output_format="yaml",
        output_context=None,
    )
    version = await storage.approve(
        stage.id, expected_attempt_id=attempt.id, reviewer_user_id="u", comment=""
    )
    db.commit()
    session = AsyncSessionAdapter(db)
    chain = generation_services(AiGenerateTaskRepository(session)).chain
    view = await build_chain_view(session, "r", "ui", task, detail=True)
    leaf = view.stages[-1]
    assert leaf.stage == "ui_yaml" and leaf.latest_version is None
    with pytest.raises(AppError):
        await version_detail(session, task, "ui", version.version_id)
    with pytest.raises(AppError):
        await chain.import_options("r", "ui", version.version_id, "u")
