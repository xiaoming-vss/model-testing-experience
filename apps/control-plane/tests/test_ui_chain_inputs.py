"""UI chain input selection, immutable provenance and refresh boundaries."""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from support.ai_execution import db as db  # noqa: F401
from support.generation import generation_services
from support.ui_generation_flow import publish, read, setup

from testing_agent.core.errors import AppError
from testing_agent.domain.ai_execution_intent import ExecutionIntent
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generate_task_source_archive import AiGenerateTaskSourceArchive
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.worker_task import WorkerTask
from testing_agent.schemas.generation_chain import (
    GenerationChainReviewRequest,
    GenerationChainRunRequest,
)
from testing_agent.services.ai_execution import worker_input


def prepare(db):
    _, _, _, repo = setup(db)
    db.add(
        AiGenerateTask(
            task_id="input-task",
            task_type="ui_case_generate",
            name="Inputs",
            project_id="p",
            sprint_id="s",
            requirement_id="r",
            creator_user_id="u",
            source_type="source_archive",
            source_content="",
            instruction="",
        )
    )
    db.flush()
    archive = AiGenerateTaskSourceArchive(
        archive_id="archive",
        task_id="input-task",
        file_id="file-1",
        filename="first.zip",
        size_bytes=20,
        sha256="a" * 64,
        uploaded_at=datetime.now(UTC),
    )
    db.add_all([archive, FunctionTestSuite(suite_id="fs", requirement_id="r", name="功能")])
    db.flush()
    case = FunctionTestCase(
        case_id="C1",
        suite_id="fs",
        title="显示记录名称",
        content=read("cases")[0]["content"],
    )
    db.add_all(
        [case, FunctionTestCase(case_id="C2", suite_id="fs", title="其他", steps="其他操作")]
    )
    db.commit()
    return generation_services(repo), archive, case


async def start(bundle, *, ids=None, refresh=False, request_id=None):
    return await bundle.chain.run_stage(
        "r",
        "ui",
        "ui_surface",
        GenerationChainRunRequest(
            connection_id="llm",
            function_case_ids=ids,
            refresh_inputs=refresh,
            request_id=request_id or uuid4(),
        ),
        "u",
    )


async def approve_surface(db, bundle, chain):
    run = await bundle.repository.get_run(chain.run_id)
    dispatch = await bundle.repository.get_latest_ai_dispatch(run.run_id)
    worker = db.scalar(select(WorkerTask).where(WorkerTask.task_id == dispatch.task_id))
    publish(
        db, run, worker, "ui_surface", {**(run.config_json or {}), "uiSurface": read("surface")}
    )
    approved = await bundle.chain.review_stage(
        "r",
        "ui",
        "ui_surface",
        GenerationChainReviewRequest(action="approve"),
        "u",
    )
    return approved, worker


async def test_first_stage_freezes_selected_cases_and_archive_and_rejects_invalid_selection(db):
    bundle, _, _ = prepare(db)
    for ids in ([], ["C1", "C1"], ["other-requirement"]):
        with pytest.raises(AppError):
            await start(bundle, ids=ids)
        await bundle.repository.rollback()
    chain = await start(bundle, ids=["C1"])
    assert (await start(bundle, ids=["C1"], request_id=chain.run_id)).run_id == chain.run_id
    assert chain.source_inputs.archive.filename == "first.zip"
    assert [c["caseId"] for c in chain.source_inputs.cases] == ["C1"]
    run = await bundle.repository.get_run(chain.run_id)
    assert run.snapshot_json["sourceArchiveFileId"] == "file-1"
    assert len(run.snapshot_json["functionalCases"]) == 1


async def test_refresh_preserves_history_and_requires_upstreams_from_new_input_run(db):
    bundle, archive, case = prepare(db)
    initial = await start(bundle, ids=["C1"])
    first, old_worker = await approve_surface(db, bundle, initial)
    version_id = first.stages[0].latest_version.version_id
    original_source = deepcopy(first.source_inputs)
    # A fully approved downstream design must also become stale after input refresh.
    designed = await bundle.chain.run_stage(
        "r",
        "ui",
        "ui_design",
        GenerationChainRunRequest(connection_id="llm"),
        "u",
    )
    design_run = await bundle.repository.get_run(designed.run_id)
    design_dispatch = await bundle.repository.get_latest_ai_dispatch(design_run.run_id)
    design_worker = db.scalar(
        select(WorkerTask).where(WorkerTask.task_id == design_dispatch.task_id)
    )
    publish(
        db,
        design_run,
        design_worker,
        "ui_design",
        {**design_run.config_json, "uiDesign": read("design")},
    )
    await bundle.chain.review_stage(
        "r",
        "ui",
        "ui_design",
        GenerationChainReviewRequest(action="approve"),
        "u",
    )
    archive.file_id = "file-2"
    archive.filename = "second.zip"
    case.title = "更新后的目标"
    db.commit()
    assert (await bundle.chain.chain("r", "ui", "u")).source_changed
    rerun = await bundle.chain.run_stage(
        "r",
        "ui",
        "ui_surface",
        GenerationChainRunRequest(connection_id="llm"),
        "u",
    )
    assert rerun.source_inputs == original_source
    await approve_surface(db, bundle, rerun)
    request_id = uuid4()
    refreshed = await start(bundle, ids=["C2"], refresh=True, request_id=request_id)
    assert refreshed.run_id != first.run_id
    assert not refreshed.source_changed
    assert refreshed.source_inputs.archive.filename == "second.zip"
    assert [c["caseId"] for c in refreshed.source_inputs.cases] == ["C2"]
    assert refreshed.stages[0].state == "running"
    assert refreshed.stages[1].blocked_reason
    assert refreshed.stages[1].state == "invalid"
    assert refreshed.stages[1].versions
    assert any(v.version_id == version_id for v in refreshed.stages[0].versions)
    assert (
        await start(bundle, ids=["C2"], refresh=True, request_id=request_id)
    ).run_id == refreshed.run_id
    detail = await bundle.chain.version("r", "ui", version_id, "u")
    assert detail.source_inputs == original_source
    assert (
        worker_input(db, await bundle.repository.get_run(first.run_id), old_worker)[0][
            "functionalCases"
        ][0]["title"]
        == "显示记录名称"
    )
    new_run = await bundle.repository.get_run(refreshed.run_id)
    dispatch = await bundle.repository.get_latest_ai_dispatch(new_run.run_id)
    worker = db.scalar(select(WorkerTask).where(WorkerTask.task_id == dispatch.task_id))
    worker.status = new_run.status = "failed"
    await bundle.execution.save(
        bundle.repository.session, new_run, intent=ExecutionIntent(actor_id="u"), worker=worker
    )
    await bundle.repository.commit()
    with pytest.raises(AppError, match="输入已更换"):
        await bundle.chain.run_stage(
            "r",
            "ui",
            "ui_design",
            GenerationChainRunRequest(
                connection_id="llm",
                upstream_versions={"ui_surface": version_id},
            ),
            "u",
        )


async def test_refresh_is_first_stage_only_and_blocks_while_running(db):
    bundle, _, _ = prepare(db)
    await start(bundle, ids=["C1"])
    with pytest.raises(AppError):
        await start(bundle, ids=["C2"], refresh=True)
    await bundle.repository.rollback()
    with pytest.raises(AppError):
        await bundle.chain.run_stage(
            "r",
            "ui",
            "ui_design",
            GenerationChainRunRequest(
                connection_id="llm",
                refresh_inputs=True,
                function_case_ids=["C1"],
            ),
            "u",
        )


async def test_refresh_invalidates_previous_unreviewed_outputs_but_keeps_their_snapshot(db):
    bundle, _, _ = prepare(db)
    chain = await start(bundle, ids=["C1"])
    run = await bundle.repository.get_run(chain.run_id)
    dispatch = await bundle.repository.get_latest_ai_dispatch(run.run_id)
    worker = db.scalar(select(WorkerTask).where(WorkerTask.task_id == dispatch.task_id))
    publish(
        db, run, worker, "ui_surface", {**(run.config_json or {}), "uiSurface": read("surface")}
    )
    stage = await bundle.chain.repository.stage(run.run_id, "ui_surface")
    attempt = await bundle.chain.repository.attempt(stage.current_artifact_attempt_id)
    frozen = deepcopy(attempt.input_snapshot_json)
    refreshed = await start(bundle, ids=["C2"], refresh=True)
    assert refreshed.run_id != run.run_id
    assert attempt.invalidated_at is not None
    assert attempt.input_snapshot_json == frozen
    assert attempt.output_content
