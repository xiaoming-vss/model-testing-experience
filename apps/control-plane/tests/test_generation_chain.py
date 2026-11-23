"""Generation chain version semantics over the real attempt ledger."""

import json

import pytest
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db
from support.generation import generation_services

from testing_agent.core.errors import AppError
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository


def services(session):
    return generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(session)))


async def test_requirement_bound_api_rejects_direct_launch(db):  # noqa: F811
    from testing_agent.domain.api_interface import path_key
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.api_interface import ApiInterface
    from testing_agent.models.software_repository import SoftwareRepository

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
