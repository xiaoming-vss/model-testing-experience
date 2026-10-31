"""Functional inputs select approved understanding versions instead of a mutable binding."""

import pytest
from support.ai_execution import AsyncSessionAdapter, create_run, db, event  # noqa: F401
from support.generation import generation_services
from support.requirement_versions import understanding_version
from support.generation_chain import latest_worker

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.requirement import Requirement
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.schemas.generation_chain import (
    GenerationChainReviewRequest,
    GenerationChainRunRequest,
)
from testing_agent.services.ai_execution import worker_input
from testing_agent.services.ai_task_output import build_generate_run_snapshot


async def test_snapshot_defaults_latest_and_allows_explicit_older_version(db):  # noqa: F811
    create_run(db)
    old = understanding_version(db, content="approved v1")
    latest = understanding_version(db, version_no=2, content="approved v2")
    requirement = db.query(Requirement).filter_by(requirement_id="r").one()
    requirement.document_content = "bound enhanced text must not be read"
    db.commit()
    repository = AiGenerateTaskRepository(AsyncSessionAdapter(db))
    task = db.query(AiGenerateTask).filter_by(task_id="task").one()
    for selected_id, expected in [("", latest), (old.version_id, old)]:
        snapshot = await build_generate_run_snapshot(
            repository, "function", task, "new-run", understanding_version_id=selected_id
        )
        assert snapshot["sourceContent"] == expected.artifact_content
        assert snapshot["requirementUnderstandingVersion"]["versionId"] == expected.version_id
        assert not snapshot.get("documentDownloadUrl")
    db.add(Requirement(requirement_id="foreign", sprint_id="s", name="other"))
    db.commit()
    foreign = understanding_version(db, "foreign")
    with pytest.raises(AppError, match="不属于当前需求"):
        await build_generate_run_snapshot(
            repository, "function", task, "new-run", understanding_version_id=foreign.version_id
        )


@pytest.mark.parametrize("content", ["", " \n ", '{"artifactType":"requirement_understanding",'])
async def test_empty_or_malformed_approved_content_is_rejected(db, content):  # noqa: F811
    create_run(db)
    understanding_version(db, content=content)
    task = db.query(AiGenerateTask).filter_by(task_id="task").one()
    with pytest.raises(AppError, match="需求理解版本内容"):
        await build_generate_run_snapshot(
            AiGenerateTaskRepository(AsyncSessionAdapter(db)), "function", task, "new-run"
        )


async def test_bound_text_without_approved_version_is_rejected(db):  # noqa: F811
    create_run(db)
    requirement = db.query(Requirement).filter_by(requirement_id="r").one()
    requirement.document_content = "existing enhanced text"
    db.commit()
    task = db.query(AiGenerateTask).filter_by(task_id="task").one()
    with pytest.raises(AppError, match="审核通过需求理解"):
        await build_generate_run_snapshot(
            AiGenerateTaskRepository(AsyncSessionAdapter(db)), "function", task, "new-run"
        )


async def test_first_launch_freezes_explicit_version_and_records_upstream(db):  # noqa: F811
    run, worker = create_run(db)
    event(db, run, worker, status="success", stage="completed", output="[]")
    old = understanding_version(db, content="selected v1")
    understanding_version(db, version_no=2, content="latest v2")
    task = db.query(AiGenerateTask).filter_by(task_id="task").one()
    db.add(
        AiGenerateTask(
            task_id="fresh-function",
            task_type=task.task_type,
            name="fresh",
            project_id="p",
            sprint_id="s",
            requirement_id="r",
            creator_user_id="u",
            source_type="requirement",
            source_content="",
        )
    )
    db.commit()
    bundle = generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(db)))
    chain = await bundle.chain.run_stage(
        "r",
        "function",
        "requirement_analysis",
        GenerationChainRunRequest(
            connection_id="llm", upstream_versions={"feature_understanding": old.version_id}
        ),
        "u",
    )
    current = await bundle.chain.repository.latest_run("fresh-function")
    dispatch = latest_worker(db, current.run_id)
    source, config = worker_input(db, current, dispatch)
    assert source["sourceContent"] == "selected v1"
    attempt = await bundle.chain.repository.attempt_by_worker(dispatch.task_id)
    assert attempt.input_snapshot_json["versioning"]["upstreamVersions"] == {
        "feature_understanding": old.version_id
    }
    assert "resultYaml" not in config
    event(
        db,
        current,
        dispatch,
        status="waiting_review",
        stage="requirement_analysis",
        config={"requirementAnalysis": {"purpose": "selected analysis", "modules": []}},
    )
    approved = await bundle.chain.review_stage(
        "r", "function", "requirement_analysis", GenerationChainReviewRequest(action="approve"), "u"
    )
    version_id = approved.stages[0].latest_version.version_id
    detail = await bundle.chain.version("r", "function", version_id, "u")
    assert detail.upstream_versions == {"feature_understanding": old.version_id}
    assert detail.upstream[0].label == "v1"
    understanding_version(db, version_no=3, content="new latest v3")
    await bundle.chain.run_stage(
        "r", "function", "case_names", GenerationChainRunRequest(connection_id="llm"), "u"
    )
    assert (
        worker_input(db, current, latest_worker(db, current.run_id))[0]["sourceContent"]
        == "selected v1"
    )
    assert chain.stages[0].upstream_stages == ["feature_understanding"]
    event(
        db,
        current,
        latest_worker(db, current.run_id),
        status="waiting_review",
        stage="case_names",
        config={"caseNames": {"categories": []}},
    )
    await bundle.chain.run_stage(
        "r", "function", "requirement_analysis", GenerationChainRunRequest(connection_id="llm"), "u"
    )
    source, _ = worker_input(db, current, latest_worker(db, current.run_id))
    assert source["sourceContent"] == "new latest v3"
