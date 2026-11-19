"""Direct-stage transaction and worker/view regression tests."""

import json

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db
from support.direct_stage_storage import (
    SCOPE_ANALYSIS,
    setup_stage,
)

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generation_stage import AiGenerationStage


async def test_unconfigured_chain_view_does_not_create_stages(db):  # noqa: F811
    from testing_agent.services.stage_storage.chain_view import build_chain_view

    seed_task(db)
    before = len(db.scalars(select(AiGenerationStage)).all())
    view = await build_chain_view(AsyncSessionAdapter(db), "r", "api", None, detail=True)
    assert [stage.stage for stage in view.stages] == [
        "interface_extract",
        "api_design",
        "generate",
    ]
    assert not view.configured
    assert len(db.scalars(select(AiGenerationStage)).all()) == before


async def test_requirement_material_runs_independently_of_the_review_stage(db):  # noqa: F811
    import json

    from support.generation import generation_services
    from support.requirement_analysis import example

    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.models.requirement import Requirement
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.schemas.generation_chain import (
        GenerationChainReviewRequest,
        GenerationChainRunRequest,
    )
    from testing_agent.schemas.workers import WorkerTaskEventRequest
    from testing_agent.services.stage_storage.commands import DirectStageCommands
    from testing_agent.services.stage_storage.worker_events import apply_stage_completion

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
    extracting_stage = next(item for item in first.stages if item.stage == "extracting_text")
    extracting = db.get(AiGenerationAttempt, extracting_stage.active_run_id)
    assert extracting.input_snapshot_json["source"]["documentFileId"] == "document-file"
    assert extracting.input_snapshot_json["source"]["workflowVersion"] == 2
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == extracting.worker_task_id))
    frozen = extracting.input_snapshot_json
    await apply_stage_completion(
        session,
        queue,
        stage_id=stage.id,
        attempt_id=extracting.id,
        kind="requirement_analysis",
        stage="extracting_text",
        source=frozen["source"],
        frozen_config=frozen["config"],
        body=WorkerTaskEventRequest(
            worker_id="worker",
            status="success",
            config_json=frozen["config"],
            output_yaml=json.dumps(example("readable-material"), ensure_ascii=False),
        ),
    )
    db.commit()
    approved = await commands.review(
        "r",
        "requirement_analysis",
        "extracting_text",
        GenerationChainReviewRequest(action="approve", expectedAttemptId=extracting.id),
        "u",
    )
    assert [item.stage for item in approved.stages] == [
        "requirement_review",
        "extracting_text",
    ]
    assert approved.stages[0].state == "not_started"
    material = approved.stages[1]
    assert material.state == "approved"
    assert material.latest_version.version_id


async def test_requirement_review_is_advisory_and_does_not_block_material(db):  # noqa: F811
    import json
    from pathlib import Path

    from support.generation import generation_services

    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.models.requirement import Requirement
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.schemas.generation_chain import (
        GenerationChainReviewRequest,
        GenerationChainRunRequest,
    )
    from testing_agent.schemas.workers import WorkerProgressRequest
    from testing_agent.services.stage_storage.commands import DirectStageCommands
    from testing_agent.services.stage_storage.worker_events import apply_stage_progress

    review_artifact = json.loads(
        (Path(__file__).parent / "fixtures/requirement_review/blocked.example.json").read_text()
    )
    stage, storage = setup_stage(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    requirement = db.scalar(select(Requirement).where(Requirement.requirement_id == "r"))
    task.task_type, stage.stage = "requirement_analysis", "requirement_review"
    requirement.document_file_id = "document-file"
    db.commit()
    session = AsyncSessionAdapter(db)
    chain = generation_services(AiGenerateTaskRepository(session)).chain
    commands = DirectStageCommands(chain)
    first = await commands.run(
        "r",
        "requirement_analysis",
        "requirement_review",
        GenerationChainRunRequest(connectionId="llm", instruction="参考接口说明"),
        "u",
    )
    review_stage = next(item for item in first.stages if item.stage == "requirement_review")
    attempt = db.get(AiGenerationAttempt, review_stage.active_run_id)
    assert attempt.input_snapshot_json["source"]["instruction"] == "参考接口说明"
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == attempt.worker_task_id))
    frozen = attempt.input_snapshot_json
    await apply_stage_progress(
        session,
        queue,
        stage_id=stage.id,
        attempt_id=attempt.id,
        kind="requirement_analysis",
        stage="requirement_review",
        source=frozen["source"],
        frozen_config=frozen["config"],
        body=WorkerProgressRequest(
            worker_id="worker",
            current_stage="requirement_review",
            stage_status="waiting_review",
            config_json={"reviewOutput": review_artifact},
            result_summary_json={"reviewStatus": "blocked", "blockerCount": 1},
        ),
    )
    db.commit()
    approved = await commands.review(
        "r",
        "requirement_analysis",
        "requirement_review",
        GenerationChainReviewRequest(action="approve", expectedAttemptId=attempt.id),
        "u",
    )
    review_view = next(item for item in approved.stages if item.stage == "requirement_review")
    assert review_view.state == "approved"
    assert review_view.latest_version
    # A blocked report does not gate the independent material stage.
    material = await commands.run(
        "r",
        "requirement_analysis",
        "extracting_text",
        GenerationChainRunRequest(connectionId="llm"),
        "u",
    )
    material_stage = next(item for item in material.stages if item.stage == "extracting_text")
    extraction_attempt = db.get(AiGenerationAttempt, material_stage.active_run_id)
    assert "reviewOutput" not in extraction_attempt.input_snapshot_json["config"]
    assert extraction_attempt.input_snapshot_json["versioning"]["upstreamVersions"] == {}


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

    first = await approve(analysis, "first", json.dumps(SCOPE_ANALYSIS), "json", {})
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
