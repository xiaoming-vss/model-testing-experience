"""Stage editors validate using the same artifact contracts as generation."""

import json

import pytest
from support.ai_execution import AsyncSessionAdapter  # noqa: F401
from support.ai_execution import db as db
from support.requirement_analysis import example

from testing_agent.core.errors import AppError
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.generation_artifact_validation import validate_generation_artifact


async def test_requirement_artifact_requires_its_contract(db):  # noqa: F811
    repository = AiGenerateTaskRepository(AsyncSessionAdapter(db))
    content, format_ = await validate_generation_artifact(
        repository,
        "requirement_analysis",
        "extracting_text",
        json.dumps(example("readable-material")),
        {},
    )
    assert format_ == "json"
    assert json.loads(content)["schemaVersion"]
    with pytest.raises(AppError):
        await validate_generation_artifact(
            repository, "requirement_analysis", "extracting_text", "{}", {}
        )


async def test_function_stage_rejects_invalid_json(db):  # noqa: F811
    repository = AiGenerateTaskRepository(AsyncSessionAdapter(db))
    with pytest.raises(AppError):
        await validate_generation_artifact(repository, "function", "case_names", "{bad", {})
    with pytest.raises(AppError):
        await validate_generation_artifact(repository, "function", "case_names", "[]", {})


async def test_test_scope_edit_validates_references_and_rejects_legacy(db):  # noqa: F811
    repository = AiGenerateTaskRepository(AsyncSessionAdapter(db))
    value = {
        "schemaVersion": "1.0",
        "artifactType": "test_scope_impact_risk",
        "testObjects": [
            {
                "id": "TO1",
                "name": "记录",
                "type": "数据",
                "description": "关注记录",
                "sourceBlockIds": ["b1"],
                "basisStatus": "confirmed",
            }
        ],
        "impactAreas": [],
        "risks": [],
        "openQuestions": [],
    }
    source = {"sourceContent": json.dumps({"materialBlocks": [{"id": "b1"}], "questions": []})}
    content, _ = await validate_generation_artifact(
        repository, "function", "requirement_analysis", json.dumps(value), source
    )
    assert json.loads(content) == value
    value["testObjects"][0]["sourceBlockIds"] = ["missing"]
    with pytest.raises(AppError):
        await validate_generation_artifact(
            repository, "function", "requirement_analysis", json.dumps(value), source
        )
    legacy = {"functionalOverview": {"purpose": "历史"}}
    with pytest.raises(AppError):
        await validate_generation_artifact(
            repository, "function", "requirement_analysis", json.dumps(legacy), {}
        )


def test_downstream_rejects_old_analysis_and_accepts_current_contract():
    from testing_agent.domain.test_scope_analysis import parse_test_scope

    current = {
        "schemaVersion": "1.0",
        "artifactType": "test_scope_impact_risk",
        "testObjects": [],
        "impactAreas": [],
        "risks": [],
        "openQuestions": [],
    }
    assert parse_test_scope(json.dumps(current)) == current
    with pytest.raises(ValueError, match="重新生成并审核"):
        parse_test_scope(json.dumps({"functionalOverview": {}}))
