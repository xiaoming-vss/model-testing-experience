"""Functional inputs select approved understanding versions instead of a mutable binding."""

import json
from pathlib import Path

import pytest
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db
from support.generation import generation_services
from support.requirement_versions import scope_artifact
from support.requirement_versions import understanding_version as legacy_version

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.requirement import Requirement
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.schemas.generation_chain import (
    GenerationChainReviewRequest,
    GenerationChainRunRequest,
)
from testing_agent.services.ai_task_output import build_generate_run_snapshot


def material_version(db, requirement_id="r", version_no=1, content=None):
    fixture_path = Path("tests/fixtures/requirement_artifacts/readable-material.example.json")
    fixture = json.loads(fixture_path.read_text())
    if content is None:
        fixture["title"] = f"材料 v{version_no}"
        content = json.dumps(fixture, ensure_ascii=False)
    row = legacy_version(db, requirement_id, version_no, content)
    row.stage = "extracting_text"
    row.artifact_format = "json"
    db.commit()
    return row


async def test_snapshot_defaults_latest_and_allows_explicit_older_version(db):  # noqa: F811
    seed_task(db)
    old = material_version(
        db,
    )
    latest = material_version(db, version_no=2)
    requirement = db.query(Requirement).filter_by(requirement_id="r").one()
    requirement.document_content = "bound enhanced text must not be read"
    db.commit()
    repository = AiGenerateTaskRepository(AsyncSessionAdapter(db))
    task = db.query(AiGenerateTask).filter_by(task_id="task").one()
    for selected_id, expected in [("", latest), (old.version_id, old)]:
        snapshot = await build_generate_run_snapshot(
            repository, "function", task, "new-run", material_version_id=selected_id
        )
        assert json.loads(snapshot["sourceContent"]) == json.loads(expected.artifact_content)
        assert snapshot["requirementMaterialVersion"]["versionId"] == expected.version_id
        assert snapshot["documentType"] == "text"
        assert not snapshot.get("documentDownloadUrl")
    db.add(Requirement(requirement_id="foreign", sprint_id="s", name="other"))
    db.commit()
    foreign = material_version(db, "foreign")
    with pytest.raises(AppError, match="不属于当前需求"):
        await build_generate_run_snapshot(
            repository, "function", task, "new-run", material_version_id=foreign.version_id
        )


@pytest.mark.parametrize("content", ["", " \n ", '{"artifactType":"requirement_understanding",'])
async def test_empty_or_malformed_approved_content_is_rejected(db, content):  # noqa: F811
    seed_task(db)
    material_version(db, content=content)
    task = db.query(AiGenerateTask).filter_by(task_id="task").one()
    with pytest.raises(AppError, match="材料整理版本内容"):
        await build_generate_run_snapshot(
            AiGenerateTaskRepository(AsyncSessionAdapter(db)), "function", task, "new-run"
        )


async def test_bound_text_without_approved_version_is_rejected(db):  # noqa: F811
    seed_task(db)
    requirement = db.query(Requirement).filter_by(requirement_id="r").one()
    requirement.document_content = "existing enhanced text"
    db.commit()
    task = db.query(AiGenerateTask).filter_by(task_id="task").one()
    with pytest.raises(AppError, match="审核通过材料整理"):
        await build_generate_run_snapshot(
            AiGenerateTaskRepository(AsyncSessionAdapter(db)), "function", task, "new-run"
        )


async def test_first_launch_freezes_explicit_version_and_records_upstream(db):  # noqa: F811
    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.services.stage_storage import DirectStageStorage
    from testing_agent.services.stage_storage.commands import DirectStageCommands
    from testing_agent.services.stage_storage.version_views import version_detail

    seed_task(db)
    old = material_version(
        db,
    )
    material_version(db, version_no=2)
    task = db.query(AiGenerateTask).filter_by(task_id="task").one()
    bundle = generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(db)))
    commands = DirectStageCommands(bundle.chain)
    view = await commands.run(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainRunRequest(
            connection_id="llm", upstream_versions={"extracting_text": old.version_id}
        ),
        "u",
    )
    current = next(item for item in view.stages if item.stage == "requirement_analysis")
    attempt = db.get(AiGenerationAttempt, current.active_run_id)
    assert json.loads(attempt.input_snapshot_json["source"]["sourceContent"])["title"] == "材料 v1"
    assert attempt.input_snapshot_json["versioning"]["upstreamVersions"] == {
        "extracting_text": old.version_id
    }
    assert "resultYaml" not in attempt.input_snapshot_json["config"]
    await DirectStageStorage(AsyncSessionAdapter(db)).publish(
        attempt.stage_id,
        attempt_id=attempt.id,
        worker_task_id=attempt.worker_task_id,
        content=json.dumps(scope_artifact(), ensure_ascii=False),
        output_format="json",
        output_context=None,
    )
    db.commit()
    approved = await commands.review(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainReviewRequest(action="approve", expectedAttemptId=attempt.id),
        "u",
    )
    version_id = approved.stages[0].latest_version.version_id
    frozen = db.query(AiGenerateStageVersion).filter_by(version_id=version_id).one()
    assert frozen.artifact_context_json["functionalSource"]["documentType"] == "text"
    detail = await version_detail(AsyncSessionAdapter(db), task, "function", version_id)
    assert detail.upstream_versions == {"extracting_text": old.version_id}
    assert detail.upstream[0].label == "v1"
    material_version(db, version_no=3)
    next_view = await commands.run(
        "r", "function", "case_names", GenerationChainRunRequest(connection_id="llm"), "u"
    )
    next_stage = next(item for item in next_view.stages if item.stage == "case_names")
    next_attempt = db.get(AiGenerationAttempt, next_stage.active_run_id)
    source = next_attempt.input_snapshot_json["source"]["sourceContent"]
    assert json.loads(source)["title"] == "材料 v1"
