"""Generation chain version semantics over the real attempt ledger."""

import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, create_run, db, event  # noqa: F401
from support.generation import generation_services
from support.generation_chain import latest_worker
from support.requirement_versions import understanding_version

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_execution import AiGenerateRunStage
from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.schemas.generation_chain import (
    GenerationChainImportRequest,
    GenerationChainReviewRequest,
    GenerationChainRevisionRequest,
    GenerationChainRunRequest,
)
from testing_agent.services.ai_execution import worker_input


def setup_analysis(session):
    run, worker = create_run(session)
    understanding_version(session)
    event(
        session,
        run,
        worker,
        status="waiting_review",
        stage="requirement_analysis",
        config={
            "enhancedText": "source",
            "requirementAnalysis": {"purpose": "登录", "modules": [{"name": "账号"}]},
        },
    )
    return run, worker


def services(session):
    return generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(session)))


async def test_chain_revision_freezes_images_only_for_the_current_attempt(db):  # noqa: F811
    run, _ = setup_analysis(db)
    files = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                file_id="screenshot",
                project_id="p",
                uploaded_by="u",
                purpose="attachment",
                content_type="image/png",
                size=100,
                filename="switch.png",
            )
        ),
        attach=AsyncMock(),
    )
    bundle = generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(db)), files=files)
    await bundle.chain.revise_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainRevisionRequest(
            connection_id="llm", instruction="根据截图补充", attachment_file_ids=["screenshot"]
        ),
        "u",
    )
    worker = latest_worker(db)
    _, config = worker_input(db, run, worker)
    assert config["revisionAttachments"] == [
        {
            "fileId": "screenshot",
            "filename": "switch.png",
            "contentType": "image/png",
        }
    ]
    files.attach.assert_awaited_once()
    event(
        db,
        run,
        worker,
        status="waiting_review",
        stage="requirement_analysis",
        config={"requirementAnalysis": {"purpose": "补充后", "modules": []}},
    )
    await bundle.chain.revise_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainRevisionRequest(connection_id="llm", instruction="再补充文字"),
        "u",
    )
    assert "revisionAttachments" not in worker_input(db, run, latest_worker(db))[1]


async def build_leaf_version(session, bundle):
    run, _ = setup_analysis(session)
    first = await bundle.chain.review_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainReviewRequest(action="approve"),
        "u",
    )
    requirement_version = first.stages[0].latest_version.version_id
    await bundle.chain.run_stage(
        "r",
        "function",
        "case_names",
        GenerationChainRunRequest(connection_id="llm"),
        "u",
    )
    current_run = await bundle.chain.repository.latest_run("task")
    event(
        session,
        current_run,
        latest_worker(session),
        status="waiting_review",
        stage="case_names",
        config={
            "requirementAnalysis": {"purpose": "登录", "modules": [{"name": "账号"}]},
            "caseNames": {"categories": [{"name": "登录"}]},
        },
    )
    second = await bundle.chain.review_stage(
        "r",
        "function",
        "case_names",
        GenerationChainReviewRequest(action="approve"),
        "u",
    )
    case_names_version = second.stages[1].latest_version.version_id
    await bundle.chain.run_stage(
        "r",
        "function",
        "detailed_cases",
        GenerationChainRunRequest(connection_id="llm"),
        "u",
    )
    current_run = await bundle.chain.repository.latest_run("task")
    event(
        session,
        current_run,
        latest_worker(session),
        status="success",
        stage="detailed_cases",
        config={
            "requirementAnalysis": {"purpose": "登录", "modules": [{"name": "账号"}]},
            "caseNames": {"categories": [{"name": "登录"}]},
        },
        output="""cases:
  - module: 登录
    title: 登录成功
    preconditions: 已注册账号
    steps: 输入正确账号密码
    expected_results: 进入首页
    priority: P0
    case_type: smoke
""",
    )
    leaf = await bundle.chain.review_stage(
        "r",
        "function",
        "detailed_cases",
        GenerationChainReviewRequest(action="approve"),
        "u",
    )
    return (
        requirement_version,
        case_names_version,
        leaf.stages[2].latest_version.version_id,
        current_run,
    )


async def test_unconfigured_chain_lists_all_stages_without_creating_rows(db):  # noqa: F811
    from datetime import UTC, datetime

    from testing_agent.models.requirement import Requirement
    from testing_agent.models.sprint import Sprint

    db.add(
        Sprint(
            sprint_id="s",
            project_id="p",
            name="fixture",
            start_time=datetime(2026, 1, 1, tzinfo=UTC),
            end_time=datetime(2026, 2, 1, tzinfo=UTC),
        )
    )
    db.flush()
    db.add(Requirement(requirement_id="r", sprint_id="s", name="fixture"))
    db.commit()
    bundle = services(db)
    overview = await bundle.chain.overview("r", "u")
    assert [chain.kind for chain in overview.chains] == [
        "requirement_analysis",
        "function",
        "api",
        "ui",
    ]
    function = next(chain for chain in overview.chains if chain.kind == "function")
    assert function.configured is False
    assert [stage.stage for stage in function.stages] == [
        "requirement_analysis",
        "case_names",
        "detailed_cases",
    ]
    assert all(stage.state == "not_started" for stage in function.stages)


async def test_approve_creates_one_version_and_pauses_the_chain(db):  # noqa: F811
    run, worker = setup_analysis(db)
    bundle = services(db)
    chain = await bundle.chain.chain("r", "function", "u")
    assert chain.stages[0].state == "draft"
    assert json.loads(chain.stages[0].draft.content)["purpose"] == "登录"

    result = await bundle.chain.review_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainReviewRequest(action="approve", comment="通过"),
        "u",
    )
    stage = result.stages[0]
    assert stage.state == "approved"
    assert stage.latest_version is not None
    assert stage.latest_version.version_no == 1
    assert stage.draft is None
    assert (
        db.scalar(
            select(WorkerTask)
            .where(WorkerTask.run_id == "run")
            .order_by(WorkerTask.created_at.desc())
        ).task_id
        == worker.task_id
    )
    assert db.query(AiGenerateStageVersion).filter_by(task_id="task").count() == 1
    assert result.run_id == "run"
    paused = await bundle.chain.repository.latest_run("task")
    assert paused.status == "success"
    assert paused.current_stage == "requirement_analysis"

    # A response-loss retry returns the same version rather than creating v2.
    again = await bundle.chain.review_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainReviewRequest(action="approve"),
        "u",
    )
    assert again.stages[0].latest_version.version_no == 1
    assert db.query(AiGenerateStageVersion).filter_by(task_id="task").count() == 1


async def test_downstream_stage_explains_missing_approved_upstream(db):  # noqa: F811
    setup_analysis(db)
    bundle = services(db)
    chain = await bundle.chain.chain("r", "function", "u")
    assert chain.stages[0].blocked_reason == ""
    assert chain.stages[1].blocked_reason == "请先审核通过「测试需求分析」"
    approved = await bundle.chain.review_stage(
        "r", "function", "requirement_analysis", GenerationChainReviewRequest(action="approve"), "u"
    )
    assert approved.stages[1].blocked_reason == ""


async def test_pending_draft_does_not_mark_the_chain_busy(db):  # noqa: F811
    setup_analysis(db)
    bundle = services(db)
    chain = await bundle.chain.chain("r", "function", "u")
    assert chain.stages[0].draft is not None
    assert chain.draft_count == 1
    assert chain.active is False
    assert chain.busy is False


async def test_superseded_attempts_are_not_drafts_after_approval(db):  # noqa: F811
    setup_analysis(db)
    bundle = services(db)
    await bundle.chain.review_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainReviewRequest(action="approve"),
        "u",
    )
    for purpose in ("登录 v2", "登录 v3"):
        await bundle.chain.revise_stage(
            "r",
            "function",
            "requirement_analysis",
            GenerationChainRevisionRequest(connection_id="llm", instruction="再改一版"),
            "u",
        )
        run = await bundle.chain.repository.latest_run("task")
        event(
            db,
            run,
            latest_worker(db),
            status="waiting_review",
            stage="requirement_analysis",
            config={
                "enhancedText": "source",
                "requirementAnalysis": {"purpose": purpose, "modules": []},
            },
        )
    result = await bundle.chain.review_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainReviewRequest(action="approve"),
        "u",
    )
    stage = result.stages[0]
    assert stage.latest_version.version_no == 2
    assert stage.draft is None
    assert result.draft_count == 0
    assert result.busy is False
    detail = await bundle.chain.version("r", "function", stage.latest_version.version_id, "u")
    assert json.loads(detail.content)["purpose"] == "登录 v3"


async def test_approved_stage_without_version_keeps_recovery_draft(db):  # noqa: F811
    setup_analysis(db)
    stage = db.query(AiGenerateRunStage).filter_by(run_id="run", stage="requirement_analysis").one()
    stage.review_status = "approved"
    db.commit()
    bundle = services(db)
    chain = await bundle.chain.chain("r", "function", "u")
    assert chain.stages[0].draft is not None

    result = await bundle.chain.review_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainReviewRequest(action="approve"),
        "u",
    )
    assert result.stages[0].latest_version.version_no == 1
    assert result.stages[0].draft is None


async def test_approve_and_continue_creates_version_and_dispatches_next_stage(db):  # noqa: F811
    setup_analysis(db)
    bundle = services(db)
    result = await bundle.chain.review_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainReviewRequest(action="approve", continue_after=True, connection_id="llm"),
        "u",
    )
    assert result.stages[0].latest_version.version_no == 1
    run = await bundle.chain.repository.latest_run("task")
    assert run.status == "pending"
    assert run.current_stage == "case_names"
    workers = list(db.scalars(select(WorkerTask).where(WorkerTask.run_id == "run")))
    assert len(workers) == 2
    _, config = worker_input(db, run, workers[-1])
    assert config["requirementAnalysis"]["purpose"] == "登录"
    attempt = await bundle.chain.repository.attempt_by_worker(workers[-1].task_id)
    assert attempt.input_snapshot_json["versioning"]["upstreamVersions"] == {
        "requirement_analysis": result.stages[0].latest_version.version_id,
    }


async def test_reject_discards_candidate_and_allows_regeneration(db):  # noqa: F811
    setup_analysis(db)
    bundle = services(db)
    result = await bundle.chain.review_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainReviewRequest(action="reject", comment="补充边界"),
        "u",
    )
    assert result.stages[0].state == "not_started"
    assert result.stages[0].draft is None
    assert result.draft_count == 0
    assert result.stages[0].latest_version is None
    assert db.query(AiGenerateStageVersion).filter_by(task_id="task").count() == 0
    stage = await bundle.chain.repository.stage("run", "requirement_analysis")
    attempt = await bundle.chain.repository.attempt(stage.current_artifact_attempt_id)
    assert attempt.output_content and stage.review_comment == "补充边界"
    assert attempt.progress_json["candidateReview"]["comment"] == "补充边界"
    # Existing rejected rows predate discard markers and must behave identically.
    attempt.invalidated_at = None
    attempt.invalidated_reason = ""
    attempt.progress_json = {}
    db.commit()
    assert (await bundle.chain.chain("r", "function", "u")).stages[0].draft is None
    with pytest.raises(AppError):
        await bundle.chain.revise_stage(
            "r",
            "function",
            "requirement_analysis",
            GenerationChainRevisionRequest(connection_id="llm", instruction="补充权限边界"),
            "u",
        )
    with pytest.raises(AppError):
        await bundle.chain.review_stage(
            "r",
            "function",
            "requirement_analysis",
            GenerationChainReviewRequest(action="approve"),
            "u",
        )
    again = await bundle.chain.review_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainReviewRequest(action="reject"),
        "u",
    )
    assert again.draft_count == 0
    regenerated = await bundle.chain.run_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainRunRequest(connection_id="llm"),
        "u",
    )
    assert regenerated.stages[0].state == "running"
    assert regenerated.stages[0].draft is None
    workers = list(db.scalars(select(WorkerTask).where(WorkerTask.run_id == "run")))
    assert len(workers) == 2
    assert attempt.progress_json["candidateReview"]["comment"] == "补充边界"
    assert attempt.output_content


async def test_run_stage_seeds_selected_upstream_version(db):  # noqa: F811
    setup_analysis(db)
    bundle = services(db)
    approved = await bundle.chain.review_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainReviewRequest(action="approve"),
        "u",
    )
    version_id = approved.stages[0].latest_version.version_id
    result = await bundle.chain.run_stage(
        "r",
        "function",
        "case_names",
        GenerationChainRunRequest(
            connection_id="llm", upstream_versions={"requirement_analysis": version_id}
        ),
        "u",
    )
    assert result.stages[1].state == "running"
    run = await bundle.chain.repository.latest_run("task")
    workers = list(db.scalars(select(WorkerTask).where(WorkerTask.run_id == "run")))
    assert len(workers) == 2
    _, config = worker_input(db, run, workers[-1])
    assert config["requirementAnalysis"]["purpose"] == "登录"

    detail = await bundle.chain.version("r", "function", version_id, "u")
    assert detail.version_no == 1
    assert detail.stage == "requirement_analysis"
    assert json.loads(detail.content)["purpose"] == "登录"


async def test_run_stage_rejects_own_pending_draft(db):  # noqa: F811
    setup_analysis(db)
    bundle = services(db)
    with pytest.raises(AppError, match="当前阶段还有待审核产物"):
        await bundle.chain.run_stage(
            "r",
            "function",
            "requirement_analysis",
            GenerationChainRunRequest(connection_id="llm"),
            "u",
        )


async def test_rerun_stage_ignores_other_stage_draft(db):  # noqa: F811
    setup_analysis(db)
    bundle = services(db)
    await bundle.chain.review_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainReviewRequest(action="approve"),
        "u",
    )
    await bundle.chain.run_stage(
        "r",
        "function",
        "case_names",
        GenerationChainRunRequest(connection_id="llm"),
        "u",
    )
    event(
        db,
        await bundle.chain.repository.latest_run("task"),
        latest_worker(db),
        status="waiting_review",
        stage="case_names",
        config={
            "requirementAnalysis": {"purpose": "登录", "modules": []},
            "caseNames": {"categories": [{"name": "登录"}]},
        },
    )

    # 「测试点」有待审核产物时，上游「测试需求分析」仍可重新运行。
    result = await bundle.chain.run_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainRunRequest(connection_id="llm"),
        "u",
    )
    assert result.stages[0].state == "running"
    run = await bundle.chain.repository.latest_run("task")
    assert run.status == "pending" and run.current_stage == "requirement_analysis"


async def test_delete_version_is_hard_delete(db):  # noqa: F811
    setup_analysis(db)
    bundle = services(db)
    approved = await bundle.chain.review_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainReviewRequest(action="approve"),
        "u",
    )
    version_id = approved.stages[0].latest_version.version_id
    assert await bundle.chain.delete_version("r", "function", version_id, "u")
    assert db.query(AiGenerateStageVersion).filter_by(task_id="task").count() == 0
    chain = await bundle.chain.chain("r", "function", "u")
    assert chain.stages[0].latest_version is None


async def test_version_records_old_upstream_choice(db):  # noqa: F811
    setup_analysis(db)
    bundle = services(db)
    first = await bundle.chain.review_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainReviewRequest(action="approve"),
        "u",
    )
    old_id = first.stages[0].latest_version.version_id
    await bundle.chain.run_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainRunRequest(connection_id="llm"),
        "u",
    )
    rerun_worker = db.scalars(
        select(WorkerTask).where(WorkerTask.run_id == "run").order_by(WorkerTask.created_at.desc())
    ).first()
    event(
        db,
        await bundle.chain.repository.latest_run("task"),
        rerun_worker,
        status="waiting_review",
        stage="requirement_analysis",
        config={
            "enhancedText": "source",
            "requirementAnalysis": {"purpose": "登录 v2", "modules": []},
        },
    )
    second = await bundle.chain.review_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainReviewRequest(action="approve"),
        "u",
    )
    assert second.stages[0].latest_version.version_no == 2
    assert second.stages[0].draft is None
    await bundle.chain.run_stage(
        "r",
        "function",
        "case_names",
        GenerationChainRunRequest(
            connection_id="llm",
            upstream_versions={"requirement_analysis": old_id},
        ),
        "u",
    )
    case_worker = db.scalars(
        select(WorkerTask).where(WorkerTask.run_id == "run").order_by(WorkerTask.created_at.desc())
    ).first()
    event(
        db,
        await bundle.chain.repository.latest_run("task"),
        case_worker,
        status="waiting_review",
        stage="case_names",
        config={
            "requirementAnalysis": {"purpose": "登录", "modules": [{"name": "账号"}]},
            "caseNames": {"categories": [{"name": "登录"}]},
        },
    )
    await bundle.chain.revise_stage(
        "r",
        "function",
        "case_names",
        GenerationChainRevisionRequest(connection_id="llm", instruction="补充异常场景"),
        "u",
    )
    revision_worker = latest_worker(db)
    revision_run = await bundle.chain.repository.latest_run("task")
    _, revision_config = worker_input(db, revision_run, revision_worker)
    assert revision_config["requirementAnalysis"]["purpose"] == "登录"
    assert revision_config["caseNames"] == {"categories": [{"name": "登录"}]}
    event(
        db,
        revision_run,
        revision_worker,
        status="waiting_review",
        stage="case_names",
        config={**revision_config, "caseNames": {"categories": [{"name": "登录"}]}},
    )
    result = await bundle.chain.review_stage(
        "r",
        "function",
        "case_names",
        GenerationChainReviewRequest(action="approve"),
        "u",
    )
    version = result.stages[1].latest_version
    assert version is not None and version.based_on_old is True
    detail = await bundle.chain.version("r", "function", version.version_id, "u")
    assert detail.upstream_versions == {"requirement_analysis": old_id}


async def test_legacy_version_detail_resolves_upstream_trace(db):  # noqa: F811
    bundle = services(db)
    requirement_id, points_id, leaf_id, _ = await build_leaf_version(db, bundle)
    leaf = await bundle.chain.repository.version("task", leaf_id)
    # The historical approval migration did not store upstream mappings.
    leaf.upstream_versions_json = None
    db.add(
        AiGenerateStageVersion(
            version_id="future-points",
            task_id="task",
            stage="case_names",
            version_no=2,
            run_id="future-run",
            attempt_id="future-attempt",
            artifact_content="{}",
            artifact_format="json",
            reviewed_at=leaf.reviewed_at + timedelta(days=1),
        )
    )
    db.flush()

    detail = await bundle.chain.version("r", "function", leaf_id, "u")

    assert detail.upstream_versions == {
        "requirement_analysis": requirement_id,
        "case_names": points_id,
    }
    assert {item.version_id for item in detail.upstream} == {requirement_id, points_id}


async def test_version_detail_preserves_deleted_upstream_reference(db):  # noqa: F811
    bundle = services(db)
    _, points_id, leaf_id, _ = await build_leaf_version(db, bundle)
    leaf = await bundle.chain.repository.version("task", leaf_id)
    leaf.upstream_versions_json = {"case_names": "deleted-points"}
    db.flush()

    detail = await bundle.chain.version("r", "function", leaf_id, "u")

    assert detail.upstream_versions == {"case_names": "deleted-points"}
    assert detail.upstream == []
    assert points_id not in detail.upstream_versions.values()


async def test_import_leaf_version_records_parent_chain_and_effective_pointer(db):  # noqa: F811
    bundle = services(db)
    requirement_version, case_names_version, leaf_version_id, _ = await build_leaf_version(
        db, bundle
    )

    options = await bundle.chain.import_options("r", "function", leaf_version_id, "u")
    assert options.version_label == "v1"
    assert options.parent_versions == {
        "requirement_analysis": requirement_version,
        "case_names": case_names_version,
    }
    assert {summary.stage for summary in options.parents} == {
        "requirement_analysis",
        "case_names",
    }
    assert options.target_required is False
    assert options.targets == []

    result = await bundle.chain.import_version(
        "r",
        "function",
        leaf_version_id,
        GenerationChainImportRequest(confirm_overwrite=True),
        "u",
    )
    assert result.imported is True
    assert result.changed_case_count == 1
    assert len(result.changed_case_ids) == 1
    record = db.scalar(select(AiGenerateVersionImport))
    assert record is not None
    assert record.version_id == leaf_version_id
    assert record.parent_versions_json == {
        "requirement_analysis": requirement_version,
        "case_names": case_names_version,
    }
    assert record.changed_case_ids_json == result.changed_case_ids
    assert record.target_type == "function_suite"
    suite = db.scalar(select(FunctionTestSuite))
    assert suite is not None
    assert suite.effective_import_id == record.import_id
    refreshed = await bundle.chain.import_options("r", "function", leaf_version_id, "u")
    target = next(item for item in refreshed.targets if item.target_id == suite.suite_id)
    assert target.effective_import_id == record.import_id
    assert target.effective_import is not None
    assert target.effective_import.version_id == leaf_version_id
    assert target.effective_import.parent_versions == record.parent_versions_json
    assert target.source_deleted is False
    assert result.chain is not None
    leaf = next(stage for stage in result.chain.stages if stage.stage == "detailed_cases")
    assert leaf.state == "imported"
    assert leaf.latest_version is not None and leaf.latest_version.imported is True

    import_id = record.import_id
    await bundle.chain.delete_version("r", "function", leaf_version_id, "u")
    assert db.query(AiGenerateVersionImport).count() == 0
    assert db.get(FunctionTestSuite, suite.id) is not None
    assert db.scalar(select(FunctionTestSuite.effective_import_id)) == import_id

    await bundle.chain.run_stage(
        "r",
        "function",
        "detailed_cases",
        GenerationChainRunRequest(connection_id="llm"),
        "u",
    )
    event(
        db,
        await bundle.chain.repository.latest_run("task"),
        latest_worker(db),
        status="success",
        stage="detailed_cases",
        config={
            "requirementAnalysis": {"purpose": "登录", "modules": [{"name": "账号"}]},
            "caseNames": {"categories": [{"name": "登录"}]},
        },
        output="""cases:
  - module: 登录
    title: 登录成功
    preconditions: 已注册账号
    steps: 输入正确账号密码
    expected_results: 进入首页
    priority: P0
    case_type: smoke
""",
    )
    rerun = await bundle.chain.review_stage(
        "r",
        "function",
        "detailed_cases",
        GenerationChainReviewRequest(action="approve"),
        "u",
    )
    next_leaf = rerun.stages[2].latest_version
    assert next_leaf is not None and next_leaf.version_id != leaf_version_id
    stale_options = await bundle.chain.import_options("r", "function", next_leaf.version_id, "u")
    stale_target = next(item for item in stale_options.targets if item.target_id == suite.suite_id)
    assert stale_target.source_deleted is True
    assert stale_target.effective_import is None
    assert stale_target.effective_import_id == import_id


async def test_import_requires_complete_parent_chain(db):  # noqa: F811
    bundle = services(db)
    _, _, leaf_version_id, _ = await build_leaf_version(db, bundle)
    leaf = await bundle.chain.repository.version("task", leaf_version_id)
    assert leaf is not None
    leaf.upstream_versions_json = {"requirement_analysis": "missing-version"}
    db.commit()

    with pytest.raises(AppError, match="上游版本已删除"):
        await bundle.chain.import_options("r", "function", leaf_version_id, "u")


async def test_deleting_upstream_version_invalidates_dependent_draft(db):  # noqa: F811
    bundle = services(db)
    requirement_version, _, _, _ = await build_leaf_version(db, bundle)
    await bundle.chain.run_stage(
        "r",
        "function",
        "case_names",
        GenerationChainRunRequest(connection_id="llm"),
        "u",
    )
    current_run = await bundle.chain.repository.latest_run("task")
    event(
        db,
        current_run,
        latest_worker(db),
        status="waiting_review",
        stage="case_names",
        config={
            "requirementAnalysis": {"purpose": "登录", "modules": [{"name": "账号"}]},
            "caseNames": {"categories": [{"name": "登录"}]},
        },
    )
    chain = await bundle.chain.chain("r", "function", "u")
    case_stage = next(stage for stage in chain.stages if stage.stage == "case_names")
    assert case_stage.draft is not None
    assert case_stage.draft.invalidated is False

    deleted = await bundle.chain.delete_version("r", "function", requirement_version, "u")
    assert deleted.invalidated_draft_count == 1
    chain = await bundle.chain.chain("r", "function", "u")
    case_stage = next(stage for stage in chain.stages if stage.stage == "case_names")
    assert case_stage.draft is not None
    assert case_stage.draft.invalidated is True
    assert "上游版本已删除" in case_stage.draft.invalidated_reason
    with pytest.raises(AppError, match="上游版本已删除"):
        await bundle.chain.review_stage(
            "r",
            "function",
            "case_names",
            GenerationChainReviewRequest(action="approve"),
            "u",
        )
    with pytest.raises(AppError, match="上游版本已删除"):
        await bundle.chain.revise_stage(
            "r",
            "function",
            "case_names",
            GenerationChainRevisionRequest(connection_id="llm", instruction="补边界"),
            "u",
        )


async def test_discard_preserves_previously_approved_version(db):  # noqa: F811
    run, _ = setup_analysis(db)
    bundle = services(db)
    approved = await bundle.chain.review_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainReviewRequest(action="approve"),
        "u",
    )
    version_id = approved.stages[0].latest_version.version_id
    await bundle.chain.run_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainRunRequest(connection_id="llm"),
        "u",
    )
    event(
        db,
        run,
        latest_worker(db),
        status="waiting_review",
        stage="requirement_analysis",
        config={"requirementAnalysis": {"purpose": "新候选", "modules": [{"name": "账号"}]}},
    )
    rejected = await bundle.chain.review_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainReviewRequest(action="reject"),
        "u",
    )
    assert rejected.stages[0].state == "approved"
    assert rejected.stages[0].draft is None
    assert rejected.draft_count == 0
    assert rejected.stages[0].latest_version.version_id == version_id
    assert len(rejected.stages[0].versions) == 1
    assert db.query(AiGenerateStageVersion).filter_by(task_id="task").count() == 1


async def test_downstream_run_preserves_pending_upstream_candidate(db):  # noqa: F811
    run, _ = setup_analysis(db)
    bundle = services(db)
    approved = await bundle.chain.review_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainReviewRequest(action="approve"),
        "u",
    )
    version_id = approved.stages[0].latest_version.version_id
    await bundle.chain.run_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainRunRequest(connection_id="llm"),
        "u",
    )
    event(
        db,
        run,
        latest_worker(db),
        status="waiting_review",
        stage="requirement_analysis",
        config={"requirementAnalysis": {"purpose": "前序新候选，尚未审核", "modules": []}},
    )
    before = await bundle.chain.chain("r", "function", "u")
    draft = before.stages[0].draft
    assert draft is not None
    frozen_content, frozen_id = draft.content, draft.attempt_id
    downstream = await bundle.chain.run_stage(
        "r",
        "function",
        "case_names",
        GenerationChainRunRequest(
            connection_id="llm", upstream_versions={"requirement_analysis": version_id}
        ),
        "u",
    )
    assert downstream.stages[0].draft.content == frozen_content
    assert downstream.stages[0].draft.attempt_id == frozen_id
    worker = latest_worker(db)
    _, config = worker_input(db, run, worker)
    assert config["requirementAnalysis"]["purpose"] == "登录"
    for status in ("running", "waiting_review"):
        event(
            db,
            run,
            worker,
            status=status,
            stage="case_names",
            config={
                "requirementAnalysis": config["requirementAnalysis"],
                "caseNames": {"categories": [{"name": "登录"}]},
            },
        )
        current = await bundle.chain.chain("r", "function", "u")
        assert current.stages[0].draft.content == frozen_content
        assert current.stages[0].draft.attempt_id == frozen_id
    original = await bundle.chain.version("r", "function", version_id, "u")
    assert json.loads(original.content)["purpose"] == "登录"


async def test_understanding_dispatch_cannot_replace_pending_extraction(db):  # noqa: F811
    from copy import deepcopy

    from support.requirement_analysis import example

    from testing_agent.domain.ai_execution_intent import ExecutionIntent
    from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
    from testing_agent.services.ai_execution import persist_run

    create_run(db)  # Shared project, sprint and requirement scope.
    db.add(
        AiGenerateTask(
            task_id="analysis-task",
            task_type="requirement_analysis",
            name="需求分析",
            project_id="p",
            sprint_id="s",
            requirement_id="r",
            creator_user_id="u",
            source_type="text",
            source_content="材料",
            instruction="",
        )
    )
    db.flush()
    run = AiGenerateTaskRun(
        run_id="analysis-run",
        task_id="analysis-task",
        project_id="p",
        sprint_id="s",
        requirement_id="r",
        trigger_user_id="u",
        checkpoint_enabled=True,
        status="pending",
        current_stage="extracting_text",
        stage_status="pending",
        config_json={},
        snapshot_json={"workflowVersion": 2, "taskType": "requirement_analysis"},
    )
    worker = WorkerTask(
        domain="ai",
        task_id="analysis-worker",
        task_type="requirement_analysis",
        run_id=run.run_id,
        status="pending",
    )
    db.add_all([run, worker])
    db.flush()
    persist_run(
        db, run, worker=worker, intent=ExecutionIntent(actor_id="u", llm_connection_id="llm")
    )
    db.commit()
    initial = example("document-extraction")
    event(
        db,
        run,
        worker,
        status="waiting_review",
        stage="extracting_text",
        config={"firstStepOutput": initial},
    )
    bundle = services(db)
    approved = await bundle.chain.review_stage(
        "r",
        "requirement_analysis",
        "extracting_text",
        GenerationChainReviewRequest(action="approve"),
        "u",
    )
    upstream_id = approved.stages[0].latest_version.version_id
    await bundle.chain.run_stage(
        "r",
        "requirement_analysis",
        "extracting_text",
        GenerationChainRunRequest(connection_id="llm"),
        "u",
    )
    candidate = deepcopy(initial)
    candidate["sources"][0]["name"] = "新提取来源，待审核"
    event(
        db,
        run,
        latest_worker(db, run.run_id),
        status="waiting_review",
        stage="extracting_text",
        config={"firstStepOutput": candidate},
    )
    pending = await bundle.chain.chain("r", "requirement_analysis", "u")
    frozen = pending.stages[0].draft
    assert frozen is not None
    await bundle.chain.run_stage(
        "r",
        "requirement_analysis",
        "feature_understanding",
        GenerationChainRunRequest(
            connection_id="llm", upstream_versions={"extracting_text": upstream_id}
        ),
        "u",
    )
    worker = latest_worker(db, run.run_id)
    _, inputs = worker_input(db, run, worker)
    assert inputs["firstStepOutput"] == initial
    for status in ("running", "waiting_review"):
        event(
            db,
            run,
            worker,
            status=status,
            stage="feature_understanding",
            config={"firstStepOutput": initial},
            output=json.dumps(example("requirement-understanding"))
            if status == "waiting_review"
            else None,
        )
        current = await bundle.chain.chain("r", "requirement_analysis", "u")
        assert current.stages[0].draft.attempt_id == frozen.attempt_id
        assert current.stages[0].draft.content == frozen.content
    assert current.stages[1].draft is not None


async def test_downstream_cannot_consume_unapproved_upstream(db):  # noqa: F811
    setup_analysis(db)
    bundle = services(db)
    with pytest.raises(AppError, match="审核通过"):
        await bundle.chain.run_stage(
            "r", "function", "case_names", GenerationChainRunRequest(connection_id="llm"), "u"
        )


@pytest.mark.parametrize("action", ["approve", "reject"])
async def test_upstream_review_does_not_stop_downstream_execution(db, action):  # noqa: F811
    run, _ = setup_analysis(db)
    bundle = services(db)
    approved = await bundle.chain.review_stage(
        "r", "function", "requirement_analysis", GenerationChainReviewRequest(action="approve"), "u"
    )
    upstream_id = approved.stages[0].latest_version.version_id
    await bundle.chain.run_stage(
        "r", "function", "requirement_analysis", GenerationChainRunRequest(connection_id="llm"), "u"
    )
    event(
        db,
        run,
        latest_worker(db),
        status="waiting_review",
        stage="requirement_analysis",
        config={"requirementAnalysis": {"purpose": "新候选", "modules": []}},
    )
    await bundle.chain.run_stage(
        "r",
        "function",
        "case_names",
        GenerationChainRunRequest(
            connection_id="llm", upstream_versions={"requirement_analysis": upstream_id}
        ),
        "u",
    )
    worker = latest_worker(db)
    _, inputs = worker_input(db, run, worker)
    event(db, run, worker, status="running", stage="case_names", config=inputs)
    result = await bundle.chain.review_stage(
        "r", "function", "requirement_analysis", GenerationChainReviewRequest(action=action), "u"
    )
    refreshed = await bundle.chain.repository.latest_run("task")
    assert refreshed.status == "running"
    assert refreshed.current_stage == "case_names"
    assert result.stages[1].state == "running"
    assert result.stages[0].draft is None
    assert result.stages[0].latest_version.version_no == (2 if action == "approve" else 1)
    _, after = worker_input(db, refreshed, worker)
    assert after == inputs
    event(
        db,
        refreshed,
        worker,
        status="waiting_review",
        stage="case_names",
        config={**after, "caseNames": {"categories": [{"name": "登录"}]}},
    )
    completed = await bundle.chain.chain("r", "function", "u")
    assert completed.stages[0].draft is None
    assert completed.stages[0].latest_version.version_no == (2 if action == "approve" else 1)
    assert completed.stages[1].draft is not None


@pytest.mark.parametrize("auto_continue", [False, True])
async def test_api_two_stage_approves_extraction_then_dispatches_selected_version(
    db,  # noqa: F811
    auto_continue,
):
    from testing_agent.domain.ai_execution_intent import ExecutionIntent
    from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
    from testing_agent.schemas.workers import WorkerProgressRequest, WorkerTaskEventRequest
    from testing_agent.services.ai_execution import persist_run
    from testing_agent.services.worker_domains.ai import apply_ai_completion_to_run, apply_progress

    create_run(db)
    task = AiGenerateTask(
        task_id="api-task",
        task_type="api_case_generate",
        name="API",
        project_id="p",
        sprint_id="s",
        requirement_id="r",
        creator_user_id="u",
        source_type="openapi",
        source_content="{}",
        instruction="",
    )
    run = AiGenerateTaskRun(
        run_id="api-run",
        task_id="api-task",
        project_id="p",
        sprint_id="s",
        requirement_id="r",
        trigger_user_id="u",
        status="pending",
        checkpoint_enabled=True,
        current_stage="openapi_extract",
        stage_status="pending",
        config_json={},
        snapshot_json={"apiWorkflowVersion": "api_two_stage/1.0", "sourceContent": "{}"},
    )
    worker = WorkerTask(
        domain="ai",
        task_id="api-worker",
        task_type="api_case_generate",
        run_id="api-run",
        status="pending",
    )
    db.add_all([task, run, worker])
    db.flush()
    persist_run(
        db,
        run,
        intent=ExecutionIntent(operation="generate", llm_connection_id="llm"),
        worker=worker,
    )
    db.commit()
    apply_progress(
        run,
        worker,
        WorkerProgressRequest(
            workerId="worker",
            taskId="api-worker",
            runId="api-run",
            currentStage="openapi_extract",
            stageStatus="waiting_review",
            configJson={"apiExtraction": {"login": {"path": "/login", "method": "POST"}}},
        ),
        lease_seconds=30,
    )
    persist_run(db, run, intent=ExecutionIntent(worker_event_id=worker.task_id), worker=worker)
    db.commit()
    bundle = services(db)
    view = await bundle.chain.review_stage(
        "r",
        "api",
        "openapi_extract",
        GenerationChainReviewRequest(
            action="approve",
            continue_after=auto_continue,
            connection_id="llm",
            instruction="覆盖鉴权异常",
        ),
        "u",
    )
    version_id = view.stages[0].latest_version.version_id
    if not auto_continue:
        await bundle.chain.run_stage(
            "r",
            "api",
            "generate",
            GenerationChainRunRequest(
                connection_id="llm",
                instruction="覆盖鉴权异常",
                upstream_versions={"openapi_extract": version_id},
            ),
            "u",
        )
    source, config = worker_input(db, run, latest_worker(db, "api-run"))
    assert source["instruction"] == "覆盖鉴权异常"
    assert config["apiExtraction"]["login"]["path"] == "/login"
    final_worker = latest_worker(db, "api-run")
    apply_ai_completion_to_run(
        run,
        WorkerTaskEventRequest(
            worker_id="worker",
            status="success",
            config_json=config,
            output_yaml=(
                "cases:\n  - name: login\n    orderNo: 1\n    method: POST\n"
                "    urlTemplate: /login\n    extractRules:\n"
                "      - {name: token, source: body_jsonpath, sourceExpr: $.token, varKey: token}\n"
                "    assertRules:\n"
                "      - {name: status, assertSource: status_code, comparator: eq, "
                "expectedValue: '200'}\n"
            ),
        ),
    )
    final_worker.status = "success"
    persist_run(
        db, run, intent=ExecutionIntent(worker_event_id=final_worker.task_id), worker=final_worker
    )
    db.commit()
    view = await bundle.chain.review_stage(
        "r", "api", "generate", GenerationChainReviewRequest(action="approve"), "u"
    )
    final = await bundle.chain.repository.version(
        "api-task", view.stages[1].latest_version.version_id
    )
    assert final.upstream_versions_json == {"openapi_extract": version_id}
    assert (await bundle.chain._complete_parent_versions(task, "api", final))[
        "openapi_extract"
    ].version_id == version_id
    from testing_agent.models.api_collection import ApiCollection

    db.add(ApiCollection(collection_id="api-target", requirement_id="r", name="目标集合"))
    db.commit()
    result = await bundle.chain.import_version(
        "r",
        "api",
        final.version_id,
        GenerationChainImportRequest(target_id="api-target"),
        "u",
    )
    assert result.imported is True
    assert result.changed_case_count == 1
    from testing_agent.models.api_assert_rule import ApiAssertRule
    from testing_agent.models.api_case import ApiCase
    from testing_agent.models.api_extract_rule import ApiExtractRule

    imported_case = db.scalar(select(ApiCase).where(ApiCase.collection_id == "api-target"))
    assert imported_case.name == "login"
    assert db.scalar(select(ApiExtractRule).where(ApiExtractRule.case_id == imported_case.case_id))
    assert db.scalar(select(ApiAssertRule).where(ApiAssertRule.case_id == imported_case.case_id))
    final.artifact_context_json = {}
    final.upstream_versions_json = None
    assert await bundle.chain._complete_parent_versions(task, "api", final) == {}
    final.artifact_context_json = {"apiWorkflowVersion": "api_two_stage/1.0"}
    final.upstream_versions_json = {"openapi_extract": "deleted"}
    with pytest.raises(AppError):
        await bundle.chain._complete_parent_versions(task, "api", final)


async def test_api_first_dispatch_creates_two_stage_run(db):  # noqa: F811
    from testing_agent.models.ai_generate_task import AiGenerateTask

    create_run(db)
    db.add(
        AiGenerateTask(
            task_id="api-task",
            task_type="api_case_generate",
            name="API",
            project_id="p",
            sprint_id="s",
            requirement_id="r",
            creator_user_id="u",
            source_type="openapi",
            source_content='{"openapi":"3.0.0","paths":{}}',
            instruction="",
        )
    )
    db.commit()
    bundle = services(db)
    view = await bundle.chain.run_stage(
        "r",
        "api",
        "openapi_extract",
        GenerationChainRunRequest(connection_id="llm", instruction="只处理登录接口"),
        "u",
    )
    run = await bundle.chain.repository.latest_run("api-task")
    assert run.snapshot_json["apiWorkflowVersion"] == "api_two_stage/1.0"
    assert run.snapshot_json["instruction"] == "只处理登录接口"
    assert run.current_stage == "openapi_extract"
    assert [stage.stage for stage in view.stages] == ["openapi_extract", "generate"]
    assert view.stages[1].blocked_reason


def test_legacy_api_checkpoint_progress_remains_single_stage():
    from testing_agent.schemas.workers import WorkerProgressRequest
    from testing_agent.services.worker_domains.ai import apply_progress

    run = SimpleNamespace(
        run_id="legacy",
        checkpoint_enabled=True,
        current_stage="",
        stage_status="pending",
        status="running",
        config_json={},
        result_yaml="",
        result_summary_json={},
        error_message="",
        snapshot_json={},
    )
    worker = SimpleNamespace(
        task_type="api_case_generate",
        status="running",
        heartbeat_at=None,
        lease_expires_at=None,
        finished_at=None,
        error_message="",
    )
    for stage in ("openapi_extract", "api_case_generating"):
        apply_progress(
            run,
            worker,
            WorkerProgressRequest(
                worker_id="w", run_id="legacy", current_stage=stage, stage_status="running"
            ),
            lease_seconds=30,
        )
        assert run.current_stage == "generate"


def test_api_two_stage_rejects_wrong_stage_and_modified_upstream():
    from testing_agent.schemas.workers import WorkerProgressRequest, WorkerTaskEventRequest
    from testing_agent.services.worker_domains.ai import apply_ai_completion_to_run, apply_progress

    run = SimpleNamespace(
        run_id="r",
        checkpoint_enabled=True,
        current_stage="openapi_extract",
        stage_status="running",
        status="running",
        config_json={},
        result_yaml="",
        result_summary_json={},
        error_message="",
        snapshot_json={"apiWorkflowVersion": "api_two_stage/1.0"},
    )
    worker = SimpleNamespace(
        task_type="api_case_generate",
        status="running",
        heartbeat_at=None,
        lease_expires_at=None,
        finished_at=None,
        error_message="",
    )
    with pytest.raises(AppError):
        apply_ai_completion_to_run(
            run,
            WorkerTaskEventRequest(
                worker_id="w", status="success", output_yaml="cases: []", config_json={}
            ),
        )
    with pytest.raises(AppError):
        apply_progress(
            run,
            worker,
            WorkerProgressRequest(
                worker_id="w",
                current_stage="openapi_extract",
                stage_status="waiting_review",
                config_json={},
            ),
            lease_seconds=30,
        )
    run.current_stage = "generate"
    run.config_json = {"apiExtraction": {"a": {"path": "/a", "method": "GET"}}}
    with pytest.raises(AppError):
        apply_ai_completion_to_run(
            run,
            WorkerTaskEventRequest(
                worker_id="w",
                status="success",
                output_yaml="cases: []",
                config_json={"apiExtraction": {"b": {}}},
            ),
        )
