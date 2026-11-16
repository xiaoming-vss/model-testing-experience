"""Generation chain version semantics over the real attempt ledger."""

import json
from types import SimpleNamespace

import pytest
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db
from support.generation import generation_services

from testing_agent.core.errors import AppError
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.schemas.generation_chain import (
    GenerationChainRunRequest,
)


def services(session):
    return generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(session)))


async def test_api_first_dispatch_creates_three_stage_run(db):  # noqa: F811
    from testing_agent.domain.api_interface import path_key
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.models.api_interface import ApiInterface
    from testing_agent.models.software_repository import SoftwareRepository
    from testing_agent.services.stage_storage.commands import DirectStageCommands

    seed_task(db)
    db.add(
        SoftwareRepository(
            software_repository_id="repo-1",
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
            software_repository_id="repo-1",
            name="登录",
            method="POST",
            path="/login",
            path_key=path_key("/login"),
        )
    )
    db.add(
        AiGenerateTask(
            task_id="api-task",
            task_type="api_case_generate",
            name="API",
            project_id="p",
            sprint_id="s",
            requirement_id="r",
            creator_user_id="u",
            source_type="interface_library",
            source_content="",
            interface_ids_json=["interface-1"],
            instruction="",
        )
    )
    db.commit()
    bundle = services(db)
    with pytest.raises(AppError, match="请在需求生成链"):
        await bundle.launcher.launch("api", "api-task", {"connectionId": "llm"}, "u")
    view = await DirectStageCommands(bundle.chain).run(
        "r",
        "api",
        "interface_extract",
        GenerationChainRunRequest(
            connection_id="llm", instruction="只处理登录接口", config_json={"maxCases": 8}
        ),
        "u",
    )
    attempt = db.get(AiGenerationAttempt, view.stages[0].active_run_id)
    assert attempt.input_snapshot_json["source"]["apiWorkflowVersion"] == "api_three_stage/1.0"
    assert attempt.input_snapshot_json["source"]["instruction"] == "只处理登录接口"
    assert attempt.input_snapshot_json["config"]["maxCases"] == 8
    assert [stage.stage for stage in view.stages] == [
        "interface_extract",
        "api_design",
        "generate",
    ]
    assert view.stages[1].blocked_reason
    assert view.stages[2].blocked_reason
    assert view.stages[1].upstream_stages == ["interface_extract"]
    assert view.stages[2].upstream_stages == ["interface_extract", "api_design"]


def test_api_three_stage_rejects_wrong_stage_and_modified_upstream():
    from testing_agent.schemas.workers import WorkerTaskEventRequest
    from testing_agent.services.worker_domains.ai import apply_ai_completion_to_run

    run = SimpleNamespace(
        run_id="r",
        checkpoint_enabled=True,
        current_stage="interface_extract",
        stage_status="running",
        status="running",
        config_json={},
        result_yaml="",
        result_summary_json={},
        error_message="",
        snapshot_json={"apiWorkflowVersion": "api_three_stage/1.0"},
    )
    with pytest.raises(AppError):
        apply_ai_completion_to_run(
            run,
            WorkerTaskEventRequest(
                worker_id="w", status="success", output_yaml="cases: []", config_json={}
            ),
        )
    run.current_stage = "generate"
    extraction = {"a": {"path": "/a", "method": "GET"}}
    design = {"schemaVersion": "api_test_design/1.0", "interfaces": {}}
    run.config_json = {"apiExtraction": extraction, "apiDesign": design}
    with pytest.raises(AppError):
        apply_ai_completion_to_run(
            run,
            WorkerTaskEventRequest(
                worker_id="w",
                status="success",
                output_yaml="cases: []",
                config_json={"apiExtraction": {"b": {}}, "apiDesign": design},
            ),
        )
    with pytest.raises(AppError):
        apply_ai_completion_to_run(
            run,
            WorkerTaskEventRequest(
                worker_id="w",
                status="success",
                output_yaml="cases: []",
                config_json={"apiExtraction": extraction, "apiDesign": {"other": True}},
            ),
        )


async def test_api_design_shallow_validation_checks_extraction_interfaces():
    from testing_agent.services.generation_artifact_validation import (
        validate_generation_artifact,
    )

    extraction = {"a": {"path": "/a", "method": "GET"}}
    design = {
        "schemaVersion": "api_test_design/1.0",
        "interfaces": {
            "a": {
                "method": "GET",
                "path": "/a",
                "cases": [
                    {
                        "id": "a_positive",
                        "title": "A-正向",
                        "basis": {"kind": "positive"},
                        "expected": {"statusClass": "2xx"},
                    }
                ],
                "uncovered": [],
            }
        },
    }
    source = {"source": {}, "config": {"apiExtraction": extraction}}
    content, output_format = await validate_generation_artifact(
        None, "api", "api_design", json.dumps(design), source
    )
    assert output_format == "json" and json.loads(content) == design

    mismatch = json.loads(json.dumps(design))
    mismatch["interfaces"]["b"] = mismatch["interfaces"].pop("a")
    with pytest.raises(AppError, match="接口集合"):
        await validate_generation_artifact(None, "api", "api_design", json.dumps(mismatch), source)
