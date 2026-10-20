"""Requirement-scoped history/configuration and execution reuse the real database paths."""

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from support.ai_execution import db  # noqa: F401
from test_database_read_paths import database, seed_history  # noqa: F401

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_task import AiGenerateTask as Task
from testing_agent.models.ai_generate_task import AiGenerateTaskRun as Run
from testing_agent.models.requirement import Requirement
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.requirement_design import RequirementDesignRepository
from testing_agent.schemas.requirement_design import (
    RequirementDesignConfigurationRequest as Configuration,
)
from testing_agent.schemas.requirement_design import RequirementDesignRunRequest as Start
from testing_agent.services.ai_generate_task import AiGenerateTaskService
from testing_agent.services.requirement_design import (
    RequirementDesignService,
    has_function_generation_input,
    validate_openapi_source,
)


async def test_requirement_history_includes_all_tasks_with_stable_pagination(database):  # noqa: F811
    sync, session, sql = database
    seed_history(sync, 25)
    task = sync.query(Task).filter_by(task_id="task").one()
    other = Task(
        task_id="second",
        task_type=task.task_type,
        name="second",
        project_id="p",
        sprint_id="s",
        requirement_id="req",
        creator_user_id="u",
        source_type="text",
        source_content="large" * 100_000,
    )
    sync.add(other)
    sync.add(
        Task(
            task_id="legacy",
            task_type=task.task_type,
            name="legacy",
            project_id="p",
            sprint_id="",
            requirement_id="req",
            creator_user_id="u",
            source_type="text",
            source_content="legacy input",
        )
    )
    sync.flush()
    sync.query(Run).filter_by(run_id="run-24").update({"task_id": "second"})
    sync.query(Run).filter_by(run_id="run-23").update({"task_id": "legacy"})
    sync.commit()
    repository = RequirementDesignRepository(session)
    sql.clear()
    overview = await repository.task_summaries("req")
    assert {row["taskId"] for row in overview} == {"task", "second", "legacy"}
    assert all("sourceContent" not in row for row in overview)
    assert await repository.run_counts("req") == {
        "function": 25,
        "api": 0,
        "ui": 0,
        "requirement_analysis": 0,
    }
    first = await repository.history("req", "function", 1, 20, "all")
    second = await repository.history("req", "function", 2, 20, "all")
    assert first["total"] == second["total"] == 25
    assert first["items"][0]["taskId"] == "second"
    assert len(second["items"]) == 5
    assert not {row["runId"] for row in first["items"]} & {row["runId"] for row in second["items"]}
    assert (await repository.history("other", "function", 1, 20, "all"))["total"] == 0
    assert (await repository.history("req", "api", 1, 20, "all"))["total"] == 0
    assert all("snapshot_json" not in query for query in sql)


async def test_api_and_requirement_final_review_filters_use_their_own_stage(database):  # noqa: F811
    sync, session, _ = database
    seed_history(sync, 3)
    task = sync.query(Task).filter_by(task_id="task").one()
    from testing_agent.models.ai_generate_execution import AiGenerateRunStage as Stage

    for task_type, kind, final_stage in [
        ("api_case_generate", "api", "generate"),
        ("requirement_analysis", "requirement_analysis", "feature_understanding"),
    ]:
        task.task_type = task_type
        sync.query(Stage).update({"stage": final_stage})
        sync.query(Stage).filter_by(run_id="run-01").update({"review_status": "rejected"})
        sync.commit()
        repository = RequirementDesignRepository(session)
        assert (await repository.history("req", kind, 1, 20, "rejected"))["total"] == 1
        assert (await repository.history("req", kind, 1, 20, "approved"))["total"] == 1
        assert (await repository.history("req", kind, 1, 20, "imported"))["total"] == 1


def test_function_input_accepts_enhanced_text_and_structured_understanding():
    requirement = Requirement(document_content="# 功能理解记录\n支持用户登录及权限校验")
    assert has_function_generation_input(requirement)
    requirement.document_content = (
        Path(__file__).parent
        / "fixtures/requirement_artifacts/requirement-understanding.example.json"
    ).read_text()
    assert has_function_generation_input(requirement)
    data = json.loads(requirement.document_content)
    data["artifactType"] = "document_extraction"
    requirement.document_content = json.dumps(data)
    assert not has_function_generation_input(requirement)


def test_workspace_requests_are_strict_and_have_no_client_owned_scope():
    with pytest.raises(ValidationError):
        Configuration(projectId="foreign")
    with pytest.raises(ValidationError):
        Start(taskId="task", requestId="invalid", connectionId="llm")


async def test_default_configuration_reuses_existing_task(database, monkeypatch):  # noqa: F811
    sync, session, _ = database
    from support.ai_execution import AsyncSessionAdapter

    tasks = AiGenerateTaskService(AiGenerateTaskRepository(AsyncSessionAdapter(sync)))
    service = RequirementDesignService(tasks)

    async def scope(*args, **kwargs):
        return sync.query(Requirement).filter_by(requirement_id="req").one()

    async def owned(*args, **kwargs):
        return sync.query(Task).filter_by(task_id="task").one()

    monkeypatch.setattr(service, "scope", scope)
    monkeypatch.setattr(tasks, "owned_task", owned)

    async def access(*args, **kwargs):
        pass

    monkeypatch.setattr(tasks, "ensure_project_access", access)
    monkeypatch.setattr(tasks, "ensure_sprint_access", access)
    first = await service.configure("req", "function", Configuration(), "u")
    second = await service.configure("req", "function", Configuration(), "u")
    assert first["taskId"] == second["taskId"] == "task"
    assert sync.query(Task).count() == 1
    with pytest.raises(AppError):
        await service.configure("other", "function", Configuration(taskId="task"), "u")


async def test_workspace_start_rejects_empty_enhanced_text_and_cross_requirement(monkeypatch):
    requirement = Requirement(requirement_id="req", sprint_id="s", document_content="  \n ")

    async def sprint(*args):
        return SimpleNamespace(sprint_id="s", project_id="p")

    async def access(*args, **kwargs):
        pass

    tasks = SimpleNamespace(
        repository=SimpleNamespace(session=None, get_sprint=sprint, commit=access),
        ensure_project_access=access,
    )
    service = RequirementDesignService(tasks)

    async def scope(*args):
        return requirement

    async def owned(*args, **kwargs):
        return SimpleNamespace(task_id="task", requirement_id="req")

    monkeypatch.setattr(service, "scope", scope)
    tasks.owned_task = owned
    body = Start(taskId="task", requestId=uuid4(), connectionId="llm")
    with pytest.raises(AppError, match="有效的需求增强文本"):
        await service.start("req", "function", body, "u")
    requirement.requirement_id = "other"

    async def foreign(*args, **kwargs):
        return SimpleNamespace(task_id="task", requirement_id="other")

    tasks.owned_task = foreign
    with pytest.raises(AppError):
        await service.start("req", "api", body, "u")


async def test_run_response_loss_retry_creates_one_run_and_one_worker(database):  # noqa: F811
    sync, _, _ = database
    from support.ai_execution import AsyncSessionAdapter

    from testing_agent.models.worker_task import WorkerTask

    task = sync.query(Task).filter_by(task_id="task").one()
    task.task_type = "api_case_generate"
    sync.commit()
    service = AiGenerateTaskService(AiGenerateTaskRepository(AsyncSessionAdapter(sync)))
    request_id = str(uuid4())
    first = await service.run("api", "task", {"connectionId": "llm"}, "u", request_id=request_id)
    second = await service.run("api", "task", {"connectionId": "llm"}, "u", request_id=request_id)
    assert first["runId"] == second["runId"] == request_id
    assert sync.query(Run).count() == sync.query(WorkerTask).count() == 1
    with pytest.raises(AppError):
        await service.run("api", "task", {"connectionId": "llm"}, "u", request_id=str(uuid4()))
    assert sync.query(Run).count() == 1


async def test_first_configuration_is_durable_and_reused_on_request_retry(database):  # noqa: F811
    sync, _, _ = database
    from support.ai_execution import AsyncSessionAdapter

    service = RequirementDesignService(
        AiGenerateTaskService(AiGenerateTaskRepository(AsyncSessionAdapter(sync)))
    )
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


@pytest.mark.parametrize(
    "content", [None, "", " \n\t", '{"artifactType":"requirement_understanding",']
)
def test_function_input_rejects_empty_or_damaged_enhanced_text(content):
    assert not has_function_generation_input(Requirement(document_content=content))


async def test_workspace_starts_function_run_from_existing_enhanced_text(database):  # noqa: F811
    sync, _, _ = database
    from support.ai_execution import AsyncSessionAdapter

    requirement = sync.query(Requirement).filter_by(requirement_id="req").one()
    requirement.document_content = "# 功能理解记录\n支持用户登录及权限校验"
    sync.commit()
    service = RequirementDesignService(
        AiGenerateTaskService(AiGenerateTaskRepository(AsyncSessionAdapter(sync)))
    )
    assert (await service.overview("req", "u"))["adoptedUnderstanding"]
    run = await service.start(
        "req", "function", Start(taskId="task", requestId=uuid4(), connectionId="llm"), "u"
    )
    saved = sync.query(Run).filter_by(run_id=run["runId"]).one()
    assert saved.snapshot_json["sourceContent"] == requirement.document_content
