"""Generation chain version semantics over the real attempt ledger."""

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


async def test_api_first_dispatch_creates_two_stage_run(db):  # noqa: F811
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.services.stage_storage.commands import DirectStageCommands

    seed_task(db)
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
    with pytest.raises(AppError, match="请在需求生成链"):
        await bundle.launcher.launch("api", "api-task", {"connectionId": "llm"}, "u")
    view = await DirectStageCommands(bundle.chain).run(
        "r",
        "api",
        "openapi_extract",
        GenerationChainRunRequest(
            connection_id="llm", instruction="只处理登录接口", config_json={"maxCases": 8}
        ),
        "u",
    )
    attempt = db.get(AiGenerationAttempt, view.stages[0].active_run_id)
    assert attempt.input_snapshot_json["source"]["apiWorkflowVersion"] == "api_two_stage/1.0"
    assert attempt.input_snapshot_json["source"]["instruction"] == "只处理登录接口"
    assert attempt.input_snapshot_json["config"]["maxCases"] == 8
    assert [stage.stage for stage in view.stages] == ["openapi_extract", "generate"]
    assert view.stages[1].blocked_reason


def test_api_two_stage_rejects_wrong_stage_and_modified_upstream():
    from testing_agent.schemas.workers import WorkerTaskEventRequest
    from testing_agent.services.worker_domains.ai import apply_ai_completion_to_run

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
    with pytest.raises(AppError):
        apply_ai_completion_to_run(
            run,
            WorkerTaskEventRequest(
                worker_id="w", status="success", output_yaml="cases: []", config_json={}
            ),
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
