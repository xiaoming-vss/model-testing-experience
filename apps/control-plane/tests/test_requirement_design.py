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
from testing_agent.domain.api_interface import path_key
from testing_agent.models.ai_generate_task import AiGenerateTask as Task
from testing_agent.models.api_interface import ApiInterface
from testing_agent.models.software_repository import SoftwareRepository
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.requirement_design import RequirementDesignRepository
from testing_agent.schemas.requirement_design import (
    RequirementDesignConfigurationRequest as Configuration,
)
from testing_agent.schemas.requirement_design import RequirementDesignRunRequest as Start


def seed_api_interface(sync):
    sync.add(
        SoftwareRepository(
            software_repository_id="software-repository-1",
            project_id="p",
            name="订单服务",
            description="",
            base_path="/api/v2",
            repository_project_id="repo-1",
            repository_group_id="group-1",
            repository_instance_key="",
            repository_path="commerce/order-service",
            repository_name="order-service",
            repository_instance_url="https://gitlab.example.com",
            version=1,
            created_by_user_id="u",
        )
    )
    sync.flush()
    sync.add(
        ApiInterface(
            interface_id="interface-1",
            software_repository_id="software-repository-1",
            name="创建订单",
            method="POST",
            path="/orders",
            path_key=path_key("/orders"),
        )
    )
    sync.flush()


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
                invalidated_reason="审核未通过，候选产物已删除" if size == 3 and i == 1 else "",
            )
        )
    sync.commit()


async def test_unbound_legacy_history_is_not_in_candidate_history(database):  # noqa: F811
    sync, session, _ = database
    task = sync.query(Task).filter_by(task_id="task").one()
    from testing_agent.models.ai_generation_stage import AiGenerationStage

    seed_direct_history(sync, 3)
    for task_type, kind, final_stage in [
        ("api_case_generate", "api", "generate"),
        ("requirement_analysis", "requirement_analysis", "extracting_text"),
    ]:
        task.task_type = task_type
        sync.query(AiGenerationStage).update({"stage": final_stage})
        sync.commit()
        repository = RequirementDesignRepository(session)
        for status in ("all", "rejected", "approved", "imported"):
            assert (await repository.history("req", kind, 1, 20, status))["total"] == 0


def test_workspace_requests_are_strict_and_have_no_client_owned_scope():
    with pytest.raises(ValidationError):
        Configuration(projectId="foreign")
    with pytest.raises(ValidationError):
        Start(taskId="task", requestId="invalid", connectionId="llm")


async def test_default_configuration_ignores_legacy_task_and_reuses_new_chain(database):  # noqa: F811
    sync, _, _ = database
    service = generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(sync))).design
    first = await service.configure("req", "function", Configuration(), "u")
    second = await service.configure("req", "function", Configuration(), "u")
    assert first["taskId"] == second["taskId"] != "task"
    assert sync.query(Task).count() == 2
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


async def test_first_configuration_is_durable_and_reused_on_request_retry(database):  # noqa: F811
    sync, _, _ = database

    service = generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(sync))).design
    seed_api_interface(sync)
    body = Configuration(interfaceIds=["interface-1"])
    first = await service.configure("req", "api", body, "u")
    second = await service.configure("req", "api", body, "u")
    assert first["taskId"] == second["taskId"]
    assert sync.query(Task).filter_by(task_type="api_case_generate").count() == 1
    with pytest.raises(AppError, match="已有当前生成链"):
        await service.configure(
            "req", "api", Configuration(newConfiguration=True, interfaceIds=["interface-1"]), "u"
        )
    from testing_agent.models.generation_candidates import (
        AiGenerationStageContent,
        RequirementGenerationChain,
    )

    chain = sync.query(RequirementGenerationChain).filter_by(requirement_id="req", kind="api").one()
    assert chain.task_id == first["taskId"]
    assert {
        slot.stage
        for slot in sync.query(AiGenerationStageContent).filter_by(chain_id=chain.chain_id)
    } == {"interface_extract", "api_design", "generate"}


async def test_api_configuration_requires_interfaces(database):  # noqa: F811
    sync, _, _ = database
    service = generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(sync))).design
    with pytest.raises(AppError):
        await service.configure("req", "api", Configuration(), "u")
    with pytest.raises(AppError):
        await service.configure("req", "api", Configuration(interfaceIds=[]), "u")


async def test_api_configuration_rejects_document_source(database):  # noqa: F811
    sync, _, _ = database
    service = generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(sync))).design
    with pytest.raises(AppError, match="不再接受 OpenAPI/Swagger 文档来源"):
        await service.configure(
            "req", "api", Configuration(sourceContent='{"openapi":"3.0.0"}'), "u"
        )
