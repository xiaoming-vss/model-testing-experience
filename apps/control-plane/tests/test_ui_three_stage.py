"""Real stage/attempt persistence and service transitions for the UI workflow."""

import pytest
import yaml
from sqlalchemy import select
from support.ai_execution import db as db
from support.ui_completion import draft as completion_draft
from support.ui_generation_flow import FIXTURES, publish, read, setup

from testing_agent.core.errors import AppError
from testing_agent.domain.ai_execution_intent import ExecutionIntent
from testing_agent.domain.ui_generation_artifacts import UI_WORKFLOW_VERSION, validate_design
from testing_agent.models.worker_task import WorkerTask
from testing_agent.schemas.workers import WorkerProgressRequest, WorkerTaskEventRequest
from testing_agent.services.ai_execution import (
    graph,
    persist_run,
    project,
    require_current_worker,
    worker_input,
)
from testing_agent.services.ui_generation_contracts import validate_ui_yaml
from testing_agent.services.worker_domains.ai import (
    apply_ai_completion_to_run,
    apply_progress,
    build_snapshot,
)


async def latest_worker(db, repo, run_id):
    context = await repo.get_latest_ai_dispatch(run_id)
    return db.scalar(select(WorkerTask).where(WorkerTask.task_id == context.task_id))


async def test_each_stage_requires_review_and_preserves_effective_artifacts(db):
    run, worker, flow, repo = setup(db)
    assert [s.stage for s in graph(db, run)[0]] == ["ui_surface", "ui_design", "ui_yaml"]
    with pytest.raises(AppError):
        await flow.review_output(run.run_id, {"stage": "ui_surface", "action": "approve"}, "u")
    publish(db, run, worker, "ui_surface", {"uiSurface": read("surface")})
    assert run.status == "waiting_review"
    assert len(list(db.scalars(select(WorkerTask)))) == 1
    old_artifact = graph(db, run)[0][0].current_artifact_attempt_id
    await flow.save_output(
        run.run_id, {"stage": "ui_surface", "configJson": {"uiSurface": read("surface")}}, "u"
    )
    result = await flow.review_output(run.run_id, {"stage": "ui_surface", "action": "approve"}, "u")
    assert result["currentStage"] == "ui_design" and result["status"] == "pending"
    assert graph(db, run)[0][0].review_status == "approved"
    worker2 = await latest_worker(db, repo, run.run_id)
    _, config = worker_input(db, run, worker2)
    assert config["uiSurface"] == read("surface")
    assert graph(db, run)[0][0].current_artifact_attempt_id == old_artifact
    snapshot = await build_snapshot(repo.session, worker2)
    assert worker2.task_id in snapshot["run"]["sourceArchiveDownloadUrl"]
    with pytest.raises(AppError):
        require_current_worker(db, run, worker)
    publish(
        db, run, worker2, "ui_design", {"uiSurface": read("surface"), "uiDesign": read("design")}
    )
    await flow.review_output(run.run_id, {"stage": "ui_design", "action": "approve"}, "u")
    worker3 = await latest_worker(db, repo, run.run_id)
    assert run.current_stage == "ui_yaml"
    draft = (FIXTURES / "draft.yaml").read_text()
    event = WorkerTaskEventRequest(
        worker_id="worker",
        status="success",
        config_json={"uiSurface": read("surface"), "uiDesign": read("design")},
        result_yaml=draft,
    )
    apply_ai_completion_to_run(run, event)
    worker3.status = "success"
    persist_run(db, run, intent=ExecutionIntent(worker_event_id=worker3.task_id), worker=worker3)
    db.commit()
    assert run.status == "success" and run.review_status == "pending"
    await flow.review_output(run.run_id, {"stage": "ui_yaml", "action": "approve"}, "u")
    assert run.review_status == "approved"
    assert [s.review_status for s in graph(db, run)[0]] == ["approved"] * 3
    assert run.result_yaml == draft


async def test_revision_failure_and_retry_keep_confirmed_surface(db):
    run, worker, flow, repo = setup(db)
    publish(db, run, worker, "ui_surface", {"uiSurface": read("surface")})
    await flow.review_output(run.run_id, {"stage": "ui_surface", "action": "approve"}, "u")
    worker2 = await latest_worker(db, repo, run.run_id)
    publish(
        db, run, worker2, "ui_design", {"uiSurface": read("surface"), "uiDesign": read("design")}
    )
    first_design = graph(db, run)[0][1].current_artifact_attempt_id
    await flow.regenerate(
        run.run_id, {"stage": "ui_design", "revisionInstruction": "补充边界"}, "u"
    )
    revised = await latest_worker(db, repo, run.run_id)
    assert worker_input(db, run, revised)[1]["revisionInstruction"] == "补充边界"
    apply_ai_completion_to_run(
        run,
        WorkerTaskEventRequest(
            worker_id="worker",
            status="failed",
            config_json={},
            result_yaml="",
            error_message="模型失败",
        ),
    )
    revised.status = "failed"
    persist_run(db, run, intent=ExecutionIntent(worker_event_id=revised.task_id), worker=revised)
    db.commit()
    project(db, run)
    assert run.config_json["uiSurface"] == read("surface")
    assert graph(db, run)[0][1].current_artifact_attempt_id == first_design
    await flow.regenerate(run.run_id, {"stage": "ui_design"}, "u", retry=True)
    retry = await latest_worker(db, repo, run.run_id)
    assert worker_input(db, run, retry)[1]["revisionInstruction"] == "补充边界"
    assert worker_input(db, run, retry)[1]["uiSurface"] == read("surface")


async def test_edit_cannot_change_upstream_and_review_cannot_skip(db):
    run, worker, flow, repo = setup(db)
    publish(db, run, worker, "ui_surface", {"uiSurface": read("surface")})
    with pytest.raises(AppError):
        await flow.review_output(run.run_id, {"stage": "ui_design", "action": "approve"}, "u")
    with pytest.raises(AppError):
        await flow.save_output(
            run.run_id,
            {
                "stage": "ui_surface",
                "configJson": {"uiSurface": read("surface"), "uiDesign": read("design")},
            },
            "u",
        )
    assert len(list(db.scalars(select(WorkerTask)))) == 1
    await flow.review_output(run.run_id, {"stage": "ui_surface", "action": "reject"}, "u")
    assert run.status == "canceled" and run.review_status == "rejected"
    with pytest.raises(AppError):
        await flow.review_output(run.run_id, {"stage": "ui_surface", "action": "approve"}, "u")


@pytest.mark.parametrize("bad_stage", ["ui_design", "ui_yaml", "completed"])
def test_worker_cannot_skip_review_or_publish_future_output(db, bad_stage):
    run, worker, _, _ = setup(db)
    with pytest.raises(AppError):
        apply_progress(
            run,
            worker,
            WorkerProgressRequest(
                worker_id="w",
                current_stage=bad_stage,
                stage_status="waiting_review",
                config_json={},
            ),
            lease_seconds=30,
        )
    assert run.current_stage == "ui_surface"
    with pytest.raises(AppError):
        apply_ai_completion_to_run(
            run, WorkerTaskEventRequest(worker_id="w", status="success", result_yaml="[]")
        )


def test_user_missing_locator_does_not_exclude_design():
    assert validate_design(read("design"), read("cases"))["cases"][0]["coverage"] == "full"
    bad = read("design")
    bad["cases"][0]["preconditions"] = []
    with pytest.raises(ValueError):
        validate_design(bad, read("cases"))


def test_design_accepts_absent_assertion_and_legacy_profile():
    design = read("design")
    expectation = design["cases"][0]["steps"][0]["expectations"][0]
    expectation.update(assertion="absent", value=None)
    assert validate_design(design, read("cases"))["cases"][0]["coverage"] == "full"

    legacy = read("design")
    legacy["capabilities"]["assertions"].remove("absent")
    assert validate_design(legacy, read("cases"))["cases"][0]["coverage"] == "full"

    legacy["cases"][0]["steps"][0]["expectations"][0].update(assertion="absent", value=None)
    with pytest.raises(ValueError):
        validate_design(legacy, read("cases"))


def test_draft_can_be_reviewed_but_requires_completion_before_import():
    raw = (FIXTURES / "draft.yaml").read_text()
    validate_ui_yaml(raw)
    from testing_agent.services.ui_test_case import validate_ui_import_payload

    cases = yaml.safe_load(raw)
    with pytest.raises(AppError, match="待补充"):
        validate_ui_import_payload({"items": cases})
    step = cases[0]["stepsJson"][0]
    step.update(locatorType="test_id", locatorValue="record-name", missingFields=[])
    validate_ui_yaml(yaml.safe_dump(cases))
    assert (
        validate_ui_import_payload({"items": cases})[0]["stepsJson"][0]["locatorValue"]
        == "record-name"
    )


def test_http_stage_save_review_and_source_selection_are_wired():
    from support.ui_task_archive import (
        UiTaskRepository,
        create_ui_task,
        ui_task_client,
        upload_archive,
        zip_bytes,
    )

    repo = UiTaskRepository()
    client, _ = ui_task_client(repo)
    task_id = create_ui_task(client)
    upload_archive(client, task_id, "source.zip", zip_bytes([("page.vue", b"<div/>")]))
    rejected = client.post(
        f"/v1/ui-case-generate-tasks/{task_id}/run",
        json={"connectionId": "llm-1", "functionCaseIds": ["other-requirement-case"]},
    )
    assert rejected.status_code == 400
    started = client.post(
        f"/v1/ui-case-generate-tasks/{task_id}/run",
        json={"connectionId": "llm-1", "checkpointEnabled": False, "functionCaseIds": ["formal-1"]},
    )
    assert started.status_code == 200, started.text
    data = started.json()["data"]
    run = repo.runs[data["runId"]]
    assert data["checkpointEnabled"] is True and data["currentStage"] == "ui_surface"
    assert run.snapshot_json["functionalCases"][0]["caseId"] == "formal-1"
    surface = read("surface")
    surface["inspectionCoverage"][0]["caseIds"] = ["formal-1"]
    run.status = "waiting_review"
    run.stage_status = "waiting_review"
    run.config_json = {"uiSurface": surface}
    repo.added[-1].status = "success"
    saved = client.patch(
        f"/v1/ui-case-generate-task-runs/{run.run_id}/stage-output",
        json={"stage": "ui_surface", "configJson": {"uiSurface": surface}},
    )
    assert saved.status_code == 200, saved.text
    reviewed = client.post(
        f"/v1/ui-case-generate-task-runs/{run.run_id}/review-stage",
        json={"stage": "ui_surface", "action": "approve"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["data"]["currentStage"] == "ui_design"
    duplicate = client.post(
        f"/v1/ui-case-generate-task-runs/{run.run_id}/review-stage",
        json={"stage": "ui_surface", "action": "approve"},
    )
    assert duplicate.status_code == 400


def test_failure_cannot_move_stage_or_progress_replace_yaml(db):
    run, worker, _, _ = setup(db)
    for status in ("failed", "error"):
        with pytest.raises(AppError):
            apply_ai_completion_to_run(
                run,
                WorkerTaskEventRequest(
                    worker_id="w", status=status, snapshot_json={"currentStage": "completed"}
                ),
            )
    run.result_yaml = "prior draft"
    apply_progress(
        run,
        worker,
        WorkerProgressRequest(
            worker_id="w",
            current_stage="ui_surface",
            stage_status="running",
            config_json={},
            result_yaml="",
        ),
        lease_seconds=30,
    )
    assert run.result_yaml == "prior draft"
    with pytest.raises(AppError):
        apply_progress(
            run,
            worker,
            WorkerProgressRequest(
                worker_id="w",
                current_stage="ui_surface",
                stage_status="running",
                result_yaml="[]",
            ),
            lease_seconds=30,
        )
    assert run.current_stage == "ui_surface" and run.result_yaml == "prior draft"


def test_worker_cannot_overwrite_approved_surface(db):
    run, worker, _, _ = setup(db)
    run.current_stage = "ui_design"
    run.config_json = {"uiSurface": read("surface")}
    altered = read("surface")
    altered["unknowns"] = []
    altered["application"] = {"name": "changed"}
    with pytest.raises(AppError):
        publish(db, run, worker, "ui_design", {"uiSurface": altered, "uiDesign": read("design")})
    assert run.config_json["uiSurface"] == read("surface")


def test_new_workflow_import_rejects_pending_fields_then_accepts_completed_yaml():
    from support.ui_confirmed_suite_import_flow import UiImportRepository, ui_import_client

    repo = UiImportRepository()
    repo.cases = []
    repo.run.snapshot_json = {"uiWorkflowVersion": UI_WORKFLOW_VERSION}
    repo.run.result_yaml = (FIXTURES / "draft.yaml").read_text()
    client = ui_import_client(repo)
    rejected = client.post(
        "/v1/ui-case-generate-task-runs/run-1/import", json={"suiteId": "suite-1"}
    )
    assert rejected.status_code == 400 and "待补充" in rejected.text
    assert repo.commits == 0 and not repo.cases
    cases = yaml.safe_load(repo.run.result_yaml)
    cases[0]["stepsJson"][0].update(
        locatorType="test_id", locatorValue="record-name", missingFields=[]
    )
    repo.run.result_yaml = yaml.safe_dump(cases, allow_unicode=True)
    imported = client.post(
        "/v1/ui-case-generate-task-runs/run-1/import", json={"suiteId": "suite-1"}
    )
    assert imported.status_code == 200, imported.text
    assert repo.run.import_status == "imported"
    assert repo.cases[0].steps_json[0]["locatorValue"] == "record-name"


async def test_save_completion_data_updates_all_bindings_without_model_dispatch(db):
    run, worker, flow, repo = setup(db)
    publish(db, run, worker, "ui_surface", {"uiSurface": read("surface")})
    await flow.review_output(run.run_id, {"stage": "ui_surface", "action": "approve"}, "u")
    worker2 = await latest_worker(db, repo, run.run_id)
    config = {"uiSurface": read("surface"), "uiDesign": read("design")}
    publish(db, run, worker2, "ui_design", config)
    await flow.review_output(run.run_id, {"stage": "ui_design", "action": "approve"}, "u")
    worker3 = await latest_worker(db, repo, run.run_id)
    value = completion_draft()
    event = WorkerTaskEventRequest(
        worker_id="worker",
        status="success",
        config_json=config,
        result_yaml=yaml.safe_dump([value], allow_unicode=True),
    )
    apply_ai_completion_to_run(run, event)
    worker3.status = "success"
    persist_run(db, run, intent=ExecutionIntent(worker_event_id=worker3.task_id), worker=worker3)
    db.commit()
    previous_tasks = len(list(db.scalars(select(WorkerTask))))
    value["dataRequirements"][0]["fields"]["id"]["value"] = "0019"
    value["dataRequirements"][0]["fields"]["version"]["value"] = "version-A"
    value["dataRequirements"][0]["confirmed"] = True
    await flow.save_output(
        run.run_id,
        {"stage": "ui_yaml", "resultYaml": yaml.safe_dump([value], allow_unicode=True)},
        "u",
    )
    refreshed = await repo.get_run(run.run_id)
    rows = yaml.safe_load(refreshed.result_yaml)
    assert "'0019'" in rows[0]["stepsJson"][0]["locatorValue"]
    assert "'0019'" in rows[0]["stepsJson"][1]["locatorValue"]
    assert rows[0]["stepsJson"][1]["operationValue"] == "version-A"
    assert len(list(db.scalars(select(WorkerTask)))) == previous_tasks
    assert refreshed.review_status == "pending"
    assert refreshed.config_json == config


@pytest.mark.parametrize("review_status", ["completed", "incomplete"])
async def test_advisory_report_survives_completion_and_becomes_stale_on_edit(db, review_status):
    from hashlib import sha256

    from testing_agent.services.ai_task_output import dump_run
    from testing_agent.services.ui_test_case import validate_ui_import_payload

    run, worker, flow, repo = setup(db)
    publish(db, run, worker, "ui_surface", {"uiSurface": read("surface")})
    await flow.review_output(run.run_id, {"stage": "ui_surface", "action": "approve"}, "u")
    worker = await latest_worker(db, repo, run.run_id)
    publish(
        db, run, worker, "ui_design", {"uiSurface": read("surface"), "uiDesign": read("design")}
    )
    await flow.review_output(run.run_id, {"stage": "ui_design", "action": "approve"}, "u")
    worker = await latest_worker(db, repo, run.run_id)
    draft = (FIXTURES / "draft.yaml").read_text()
    review = {
        "status": review_status,
        "artifactSha256": sha256(draft.encode()).hexdigest(),
        "modules": [
            {
                "batch": 1,
                "module": "登录",
                "status": review_status,
                "issues": [
                    {
                        "caseIndex": 1,
                        "stepIndex": 1,
                        "code": "coverage",
                        "evidence": "待确认",
                        "repair": "保留目标核对",
                    }
                ],
            }
        ],
    }
    apply_ai_completion_to_run(
        run,
        WorkerTaskEventRequest(
            worker_id="worker",
            status="success",
            result_yaml=draft,
            config_json={"uiSurface": read("surface"), "uiDesign": read("design")},
            result_summary_json={"uiSemanticReview": review},
        ),
    )
    worker.status = "success"
    persist_run(db, run, intent=ExecutionIntent(worker_event_id=worker.task_id), worker=worker)
    db.commit()
    project(db, run)
    assert run.status == "success" and run.review_status == "pending"
    assert dump_run(run)["resultSummaryJson"]["uiSemanticReview"] == review
    # Unchanged save keeps report current; changed YAML invalidates its positional evidence.
    saved = await flow.save_output(run.run_id, {"stage": "ui_yaml", "resultYaml": draft}, "u")
    assert saved["resultSummaryJson"]["uiSemanticReview"]["status"] == review_status
    changed = draft + "\n# 人工修改草稿\n"
    saved = await flow.save_output(run.run_id, {"stage": "ui_yaml", "resultYaml": changed}, "u")
    assert saved["resultSummaryJson"]["uiSemanticReview"]["status"] == "stale"
    assert run.result_summary_json["uiSemanticReview"]["status"] == review_status
    await flow.review_output(run.run_id, {"stage": "ui_yaml", "action": "approve"}, "u")
    assert run.review_status == "approved"
    # Advisory review does not bypass formal import completeness, even after approval.
    with pytest.raises(AppError):
        validate_ui_import_payload({"items": yaml.safe_load(changed)})


async def test_chain_review_can_pause_ui_stage_without_dispatching(db):
    run, worker, flow, _ = setup(db)
    publish(db, run, worker, "ui_surface", {"uiSurface": read("surface")})
    await flow.review_output(
        run.run_id,
        {"stage": "ui_surface", "action": "approve"},
        "u",
        continue_after=False,
    )
    assert run.status == "success"
    assert run.stage_status == "completed"
    assert run.current_stage == "ui_surface"
    assert len(list(db.scalars(select(WorkerTask)))) == 1


async def test_chain_continue_and_revision_freeze_ui_stage_inputs(db):
    from support.generation import generation_services

    from testing_agent.schemas.generation_chain import (
        GenerationChainReviewRequest,
        GenerationChainRevisionRequest,
    )

    run, worker, _, repo = setup(db)
    bundle = generation_services(repo)
    publish(db, run, worker, "ui_surface", {"uiSurface": read("surface")})
    chain = await bundle.chain.review_stage(
        "r",
        "ui",
        "ui_surface",
        GenerationChainReviewRequest(action="approve", continue_after=True, connection_id="llm"),
        "u",
    )
    worker = await latest_worker(db, repo, run.run_id)
    source, config = worker_input(db, run, worker)
    assert config["uiSurface"] == read("surface")
    assert source["functionalCases"] == read("cases")
    attempt = await bundle.chain.repository.attempt_by_worker(worker.task_id)
    expected = {"ui_surface": chain.stages[0].latest_version.version_id}
    assert attempt.input_snapshot_json["versioning"]["upstreamVersions"] == expected
    publish(db, run, worker, "ui_design", {**config, "uiDesign": read("design")})
    await bundle.chain.revise_stage(
        "r",
        "ui",
        "ui_design",
        GenerationChainRevisionRequest(connection_id="llm", instruction="补充错误提示验证"),
        "u",
    )
    revision = await latest_worker(db, repo, run.run_id)
    revision_source, revision_config = worker_input(db, run, revision)
    assert revision_source["functionalCases"] == source["functionalCases"]
    assert revision_config["uiSurface"] == config["uiSurface"]
    assert revision_config["uiDesign"] == read("design")
    revised = await bundle.chain.repository.attempt_by_worker(revision.task_id)
    assert revised.input_snapshot_json["versioning"]["upstreamVersions"] == expected
