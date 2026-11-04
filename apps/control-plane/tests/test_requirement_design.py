"""Requirement-scoped history/configuration and execution reuse the real database paths."""

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from support.ai_execution import AsyncSessionAdapter  # noqa: F401
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import NOW, database  # noqa: F401
from support.generation import generation_services

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_task import AiGenerateTask as Task
from testing_agent.models.requirement import Requirement
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.requirement_design import RequirementDesignRepository
from testing_agent.schemas.requirement_design import (
    RequirementDesignConfigurationRequest as Configuration,
)
from testing_agent.schemas.requirement_design import RequirementDesignRunRequest as Start
from testing_agent.services.requirement_design import (
    validate_openapi_source,
)


def seed_direct_history(sync, size):
    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.models.ai_generation_stage import AiGenerationStage

    task_ids = {"task"}
    if size == 25:
        task_ids |= {"second", "legacy"}
    for task_id in task_ids:
        sync.add(AiGenerationStage(id="direct-" + task_id, task_id=task_id, stage="detailed_cases"))
    sync.flush()
    for i in range(size):
        task_id = (
            "second" if size == 25 and i == 24 else "legacy" if size == 25 and i == 23 else "task"
        )
        sync.add(
            AiGenerationAttempt(
                id=f"direct-attempt-{i:02d}",
                stage_id="direct-" + task_id,
                attempt_no=i + 1,
                operation="generate",
                status="success",
                requested_by="u",
                output_content="cases: ok",
                created_at=NOW + timedelta(seconds=i),
                invalidated_reason="审核未通过，候选产物已丢弃" if size == 3 and i == 1 else "",
            )
        )
    sync.commit()


async def test_api_and_requirement_final_review_filters_use_their_own_stage(database):  # noqa: F811
    sync, session, _ = database
    task = sync.query(Task).filter_by(task_id="task").one()
    from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
    from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
    from testing_agent.models.ai_generation_stage import AiGenerationStage

    seed_direct_history(sync, 3)
    version = AiGenerateStageVersion(
        version_id="version",
        task_id="task",
        stage="generate",
        version_no=1,
        attempt_id="direct-attempt-00",
        artifact_content="approved",
        artifact_format="json",
    )
    sync.add(version)
    sync.flush()
    sync.add(
        AiGenerateVersionImport(
            import_id="import-direct",
            task_id="task",
            version_id="version",
            leaf_stage="generate",
            target_type="api_collection",
            target_id="target",
            imported_by="u",
            imported_at=NOW,
        )
    )
    sync.flush()
    for task_type, kind, final_stage in [
        ("api_case_generate", "api", "generate"),
        ("requirement_analysis", "requirement_analysis", "feature_understanding"),
    ]:
        task.task_type = task_type
        sync.query(AiGenerationStage).update({"stage": final_stage})
        version.stage = final_stage
        sync.commit()
        repository = RequirementDesignRepository(session)
        assert (await repository.history("req", kind, 1, 20, "rejected"))["total"] == 1
        assert (await repository.history("req", kind, 1, 20, "approved"))["total"] == 1
        assert (await repository.history("req", kind, 1, 20, "imported"))["total"] == 1


def test_workspace_requests_are_strict_and_have_no_client_owned_scope():
    with pytest.raises(ValidationError):
        Configuration(projectId="foreign")
    with pytest.raises(ValidationError):
        Start(taskId="task", requestId="invalid", connectionId="llm")


async def test_default_configuration_reuses_existing_task(database, monkeypatch):  # noqa: F811
    sync, session, _ = database

    tasks = generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(sync)))
    service = tasks.design

    async def scope(*args, **kwargs):
        return sync.query(Requirement).filter_by(requirement_id="req").one()

    async def owned(*args, **kwargs):
        return sync.query(Task).filter_by(task_id="task").one()

    monkeypatch.setattr(service, "scope", scope)
    monkeypatch.setattr(tasks.access, "owned_task", owned)

    async def access(*args, **kwargs):
        pass

    monkeypatch.setattr(tasks.access, "ensure_project_access", access)
    monkeypatch.setattr(tasks.access, "ensure_sprint_access", access)
    first = await service.configure("req", "function", Configuration(), "u")
    second = await service.configure("req", "function", Configuration(), "u")
    assert first["taskId"] == second["taskId"] == "task"
    assert sync.query(Task).count() == 1
    with pytest.raises(AppError):
        await service.configure("other", "function", Configuration(taskId="task"), "u")


async def test_workspace_old_start_requires_stage_chain_and_checks_requirement():
    from unittest.mock import AsyncMock

    from testing_agent.handlers.requirement_design import start_requirement_design

    service = SimpleNamespace(
        scope=AsyncMock(),
        access=SimpleNamespace(
            owned_task=AsyncMock(return_value=SimpleNamespace(requirement_id="req"))
        ),
    )
    body = Start(taskId="task", requestId=uuid4(), connectionId="llm")
    with pytest.raises(AppError, match="请在需求生成链"):
        await start_requirement_design("req", "function", body, "u", service)
    service.access.owned_task.return_value.requirement_id = "other"
    with pytest.raises(AppError):
        await start_requirement_design("req", "function", body, "u", service)


async def test_stage_response_loss_retry_creates_one_attempt_and_one_worker(database):  # noqa: F811

    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.models.worker_task import WorkerTask
    from testing_agent.schemas.generation_chain import GenerationChainRunRequest
    from testing_agent.services.stage_storage.commands import DirectStageCommands

    sync, _, _ = database
    task = sync.query(Task).filter_by(task_id="task").one()
    task.task_type = "api_case_generate"
    task.source_content = '{"openapi":"3.0.0","paths":{}}'
    sync.commit()
    bundle = generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(sync)))
    commands = DirectStageCommands(bundle.chain)
    request_id = uuid4()
    body = GenerationChainRunRequest(connectionId="llm", requestId=request_id)
    first = await commands.run("req", "api", "openapi_extract", body, "u")
    second = await commands.run("req", "api", "openapi_extract", body, "u")
    assert first.stages[0].active_run_id == second.stages[0].active_run_id
    assert sync.query(AiGenerationAttempt).count() == sync.query(WorkerTask).count() == 1
    with pytest.raises(AppError):
        await commands.run(
            "req",
            "api",
            "openapi_extract",
            GenerationChainRunRequest(connectionId="llm", requestId=uuid4()),
            "u",
        )
    assert sync.query(AiGenerationAttempt).count() == 1


async def test_first_configuration_is_durable_and_reused_on_request_retry(database):  # noqa: F811
    sync, _, _ = database

    service = generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(sync))).design
    body = Configuration(sourceContent='{"openapi":"3.0.0","paths":{}}')
    first = await service.configure("req", "api", body, "u")
    second = await service.configure("req", "api", body, "u")
    assert first["taskId"] == second["taskId"]
    assert sync.query(Task).filter_by(task_type="api_case_generate").count() == 1
    different = await service.configure(
        "req",
        "api",
        Configuration(newConfiguration=True, sourceContent='{"swagger":"2.0","paths":{}}'),
        "u",
    )
    assert different["taskId"] != first["taskId"]
    assert sync.query(Task).filter_by(task_type="api_case_generate").count() == 2


@pytest.mark.parametrize("source", ["", "随便一段文字", '{"openapi":"3.0.0"}', "[:invalid"])
def test_openapi_configuration_rejects_missing_or_invalid_spec(source):
    with pytest.raises(AppError):
        validate_openapi_source(source)


@pytest.mark.parametrize(
    "source",
    [
        '{"openapi":"3.0.0","paths":{}}',
        "swagger: '2.0'\npaths: {}",
        "https://example.test/openapi.json",
    ],
)
def test_openapi_configuration_accepts_json_yaml_and_legacy_urls(source):
    validate_openapi_source(source)


async def test_workspace_starts_function_stage_from_approved_version_without_binding(database):  # noqa: F811
    from support.requirement_versions import understanding_version

    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.schemas.generation_chain import GenerationChainRunRequest
    from testing_agent.services.stage_storage.commands import DirectStageCommands

    sync, _, _ = database
    requirement = sync.query(Requirement).filter_by(requirement_id="req").one()
    requirement.document_content = ""
    sync.commit()
    version = understanding_version(sync, "req")
    bundle = generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(sync)))
    assert (await bundle.design.overview("req", "u"))["adoptedUnderstanding"]
    result = await DirectStageCommands(bundle.chain).run(
        "req",
        "function",
        "requirement_analysis",
        GenerationChainRunRequest(connectionId="llm"),
        "u",
    )
    attempt = sync.get(AiGenerationAttempt, result.stages[0].active_run_id)
    source = attempt.input_snapshot_json["source"]
    assert source["sourceContent"] == version.artifact_content
    assert source["requirementUnderstandingVersion"]["versionId"] == version.version_id
