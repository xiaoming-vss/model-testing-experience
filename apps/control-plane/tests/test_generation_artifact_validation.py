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
        json.dumps(example("document-extraction")),
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
