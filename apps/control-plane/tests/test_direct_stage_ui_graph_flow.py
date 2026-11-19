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
from testing_agent.models.ai_generation_stage import AiGenerationStage


async def test_graph_result_is_bound_to_approved_case_version(db, monkeypatch):  # noqa: F811
    from unittest.mock import AsyncMock

    from support.direct_graph import cases_output, relations_output
    from support.requirement_analysis import example

    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.schemas.ai_generate_task import AiGenerateTaskRunResponse
    from testing_agent.schemas.workers import WorkerTaskEventRequest
    from testing_agent.services.stage_storage import relations
    from testing_agent.services.stage_storage.version_delete import delete_stage_version
    from testing_agent.services.stage_storage.worker_events import apply_stage_completion

    stage, storage = setup_stage(db)
    stage.stage = "detailed_cases"
    material = example("readable-material")
    material_version = {"versionId": "frozen-material-version"}
    first = await storage.prepare(
        stage.id,
        worker_task_id="leaf",
        requested_by="u",
        input_snapshot={
            "source": {
                "sourceContent": json.dumps(material),
                "requirementMaterialVersion": material_version,
                "instruction": "用例生成指令",
            },
            "config": {"requirementAnalysis": SCOPE_ANALYSIS},
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
    graph_source = graph.input_snapshot_json["source"]
    assert set(graph_source) == {
        "sourceContent",
        "sourceFormat",
        "sourceFormatVersion",
        "requirementMaterialVersion",
    }
    assert json.loads(graph_source["sourceContent"]) == material
    assert graph_source["requirementMaterialVersion"] == material_version
    graph_config = graph.input_snapshot_json["config"]
    assert set(graph_config) == {"resultYaml"}
    assert json.loads(graph_config["resultYaml"]) == json.loads(cases_output())
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
    rerun = await relations.launch_graph(AsyncSessionAdapter(db), task, first.id, "u", "llm")
    assert rerun.input_snapshot_json["config"] == graph_config
    assert (await relations.graph_view(AsyncSessionAdapter(db), task, first))["configJson"][
        "caseRelations"
    ] == relations_output()


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
        stage.id,
        worker_task_id="worker",
        requested_by="u",
        input_snapshot={"source": TRACEABLE_SOURCE, "config": TRACEABLE_CONFIG},
    )
    await storage.publish(
        stage.id,
        attempt_id=candidate.id,
        worker_task_id="worker",
        content=json.dumps(TRACEABLE_POINTS),
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
            json={"expectedAttemptId": candidate.id, "content": json.dumps(TRACEABLE_POINTS)},
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


@pytest.mark.parametrize("has_material", [True, False])
async def test_graph_http_uses_version_attempt_identity(db, monkeypatch, has_material):  # noqa: F811
    from unittest.mock import AsyncMock

    import httpx
    from support.direct_graph import cases_output
    from support.generation import generation_services, install_generation_services
    from support.requirement_analysis import example

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
            "source": {
                "sourceContent": json.dumps(example("readable-material"))
                if has_material
                else "旧需求正文"
            },
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
        if not has_material:
            assert started.status_code == 400
            assert "缺少有效的材料整理结果" in started.json()["message"]
            return
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
