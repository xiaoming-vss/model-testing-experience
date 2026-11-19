"""Direct-stage transaction and worker/view regression tests."""

import json

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db
from support.direct_stage_storage import (
    SCOPE_ANALYSIS,
    TRACEABLE_CONFIG,
    TRACEABLE_POINTS,
    TRACEABLE_SOURCE,
    setup_stage,
)

from testing_agent.core.errors import AppError
from testing_agent.services.stage_storage import DirectStageStorage


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
        stage.id,
        worker_task_id="first",
        requested_by="u",
        input_snapshot={"source": TRACEABLE_SOURCE, "config": TRACEABLE_CONFIG},
    )
    await storage.publish(
        stage.id,
        attempt_id=attempt.id,
        worker_task_id="first",
        content=json.dumps(TRACEABLE_POINTS),
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
        GenerationChainSaveDraftRequest(
            expectedAttemptId=attempt.id, content=json.dumps(TRACEABLE_POINTS)
        ),
        "u",
    )
    point = next(item for item in saved.stages if item.stage == "case_names")
    assert json.loads(point.draft.content) == {
        **TRACEABLE_POINTS,
        "reviewStatus": "self_review_only",
    }
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
    import json
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from support.generation import generation_services
    from support.requirement_versions import material_version

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
    understanding = material_version(db)
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
        "extracting_text": understanding.version_id
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
        body.model_copy(update={"upstream_versions": {"extracting_text": "different"}}),
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
            config_json={"requirementAnalysis": SCOPE_ANALYSIS},
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
    assert second.input_snapshot_json["config"]["requirementAnalysis"] == SCOPE_ANALYSIS
    assert json.loads(second.input_snapshot_json["source"]["sourceContent"]) == json.loads(
        understanding.artifact_content
    )


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
        input_snapshot={
            "source": TRACEABLE_SOURCE,
            "config": TRACEABLE_CONFIG,
            "llmConnectionId": "llm",
        },
    )
    await storage.publish(
        stage.id,
        attempt_id=attempt.id,
        worker_task_id="first",
        content=json.dumps(TRACEABLE_POINTS),
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
    assert "测试范围风险分析" in result.continuation_error


async def test_approval_can_continue_to_next_direct_stage(db, monkeypatch):  # noqa: F811
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from support.generation import generation_services
    from support.requirement_versions import material_version

    from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.schemas.generation_chain import GenerationChainReviewRequest
    from testing_agent.services.stage_storage import commands as command_module
    from testing_agent.services.stage_storage import run_command
    from testing_agent.services.stage_storage.commands import DirectStageCommands

    stage, storage = setup_stage(db)
    material = material_version(db)
    db.add(
        AiGenerateStageVersion(
            version_id="analysis",
            task_id="task",
            stage="requirement_analysis",
            version_no=1,
            attempt_id="old",
            artifact_content=json.dumps(SCOPE_ANALYSIS),
            artifact_format="json",
            artifact_context_json={
                "functionalSource": {
                    "sourceContent": material.artifact_content,
                    "sourceFormat": "requirement_understanding_json",
                    "sourceFormatVersion": "0.2",
                    "requirementMaterialVersion": {"versionId": material.version_id},
                }
            },
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
            "source": TRACEABLE_SOURCE,
            "config": TRACEABLE_CONFIG,
            "llmConnectionId": "llm",
            "versioning": {"upstreamVersions": {"requirement_analysis": "analysis"}},
        },
    )
    await storage.publish(
        stage.id,
        attempt_id=attempt.id,
        worker_task_id="first",
        content=json.dumps(TRACEABLE_POINTS),
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
