"""Direct-stage transaction and worker/view regression tests."""

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db
from support.direct_stage_storage import (
    setup_stage,
)

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generation_stage import AiGenerationStage


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
        stage="extracting_text",
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
    frozen = {"source": {"requirementMaterialVersion": {"versionId": "understanding"}}}
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
