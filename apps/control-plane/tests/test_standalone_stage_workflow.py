"""Independent functional checkpoint commands preserve one execution and its history."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db
from support.direct_graph import cases_output, relations_output

from testing_agent.core.errors import AppError, ErrForbidden
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.schemas.workers import (
    WorkerClaimRequest,
    WorkerProgressRequest,
    WorkerTaskEventRequest,
)
from testing_agent.services import standalone_worker_authorization as worker_auth
from testing_agent.services.ai_candidate_review import GenerationCandidateReview
from testing_agent.services.ai_stage_workflow import GenerationStageWorkflow
from testing_agent.services.standalone_execution import start_standalone_execution
from testing_agent.services.standalone_execution_view import project_standalone_execution
from testing_agent.services.standalone_worker_service import StandaloneWorkerService


async def test_candidate_review_rejects_legacy_run_without_writing():
    session = SimpleNamespace(commit=AsyncMock())
    owned_run = AsyncMock(return_value=SimpleNamespace(run_id="old"))
    review = GenerationCandidateReview(SimpleNamespace(session=session), owned_run)
    with pytest.raises(AppError):
        await review.update_result("function", "old", "cases: []", "user")
    with pytest.raises(AppError):
        await review.review("function", "old", {"action": "approve"}, "user")
    session.commit.assert_not_awaited()


async def test_checkpoint_commands_do_not_mutate_legacy_runs():
    session = SimpleNamespace(commit=AsyncMock())
    service = GenerationStageWorkflow(
        repository=SimpleNamespace(session=session),
        owned_run=AsyncMock(return_value=SimpleNamespace(run_id="old")),
    )
    actions = (
        service.save_stage_output("old", {}, "user"),
        service.review_stage("old", {}, "user"),
        service.revise_function_case_stage("old", {}, "user"),
        service.retry_stage("old", {}, "user"),
        service.generate_relation_analysis("old", {}, "user"),
        service.review_api_checkpoint("old", {}, "user"),
    )
    for action in actions:
        with pytest.raises(AppError) as missing:
            await action
        assert missing.value.http_code == 404
    session.commit.assert_not_awaited()


async def test_checkpoint_edit_review_retry_and_graph_keep_execution_identity(db, monkeypatch):  # noqa: F811
    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    execution, initial, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="run",
        request_id="initial",
        actor_id="user",
        connection_id="llm",
        source={"sourceContent": "frozen"},
        config={},
        checkpoint_enabled=True,
    )
    db.commit()
    monkeypatch.setattr(worker_auth, "authorize_worker_actor", AsyncMock(return_value="user"))
    worker = StandaloneWorkerService(session)
    repository = AiGenerateTaskRepository(session)

    async def owned_run(user_id, run_id, kind=None, *, action="read"):
        return await project_standalone_execution(session, run_id)

    identifiers = iter(["third"])
    stages = GenerationStageWorkflow(
        repository=repository, owned_run=owned_run, id_factory=lambda: next(identifiers)
    )
    stages.stage_connection = AsyncMock(return_value="llm")

    async def claim(task_id):
        queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == task_id))
        await worker.claim(queue, WorkerClaimRequest(worker_id="agent"))
        await worker.started(queue, WorkerTaskEventRequest(worker_id="agent"))
        return queue

    queue = await claim("initial")
    await worker.progress(
        queue,
        WorkerProgressRequest(
            worker_id="agent",
            current_stage="requirement_analysis",
            stage_status="waiting_review",
            config_json={"requirementAnalysis": {"purpose": "initial"}},
        ),
    )
    edited = await stages.save_stage_output(
        "run",
        {
            "stage": "requirement_analysis",
            "configJson": {"requirementAnalysis": {"purpose": "edited"}},
        },
        "user",
    )
    assert edited["configJson"]["requirementAnalysis"] == {"purpose": "edited"}
    before = len(db.scalars(select(WorkerTask)).all())
    stages.stage_connection = AsyncMock(side_effect=ErrForbidden())
    with pytest.raises(AppError):
        await stages.review_stage(
            "run", {"stage": "requirement_analysis", "action": "approve"}, "user"
        )
    assert len(db.scalars(select(WorkerTask)).all()) == before
    assert (await project_standalone_execution(session, "run")).status == "waiting_review"
    stages.stage_connection = AsyncMock(return_value="llm")
    review_request = {"stage": "requirement_analysis", "action": "approve", "requestId": "second"}
    result = await stages.review_stage("run", review_request, "user")
    assert result["runId"] == execution.execution_id and result["currentStage"] == "case_names"
    replay = await stages.review_stage("run", review_request, "user")
    assert replay["runId"] == "run" and replay["currentStage"] == "case_names"
    with pytest.raises(AppError):
        await stages.review_stage("run", {**review_request, "comment": "different"}, "user")
    assert len(db.scalars(select(WorkerTask).where(WorkerTask.task_id == "second")).all()) == 1
    queue = await claim("second")
    await worker.complete(
        queue,
        WorkerTaskEventRequest(worker_id="agent", status="failed", error_message="model failed"),
    )
    retry_request = {"stage": "case_names", "requestId": "retry"}
    retried = await stages.retry_stage("run", retry_request, "user")
    assert retried["status"] == "pending" and retried["runId"] == "run"
    assert (await stages.retry_stage("run", retry_request, "user"))["status"] == "pending"
    with pytest.raises(AppError):
        await stages.retry_stage("run", {**retry_request, "stage": "detailed_cases"}, "user")
    queue = await claim("retry")
    await worker.progress(
        queue,
        WorkerProgressRequest(
            worker_id="agent",
            current_stage="case_names",
            stage_status="waiting_review",
            config_json={
                "requirementAnalysis": {"purpose": "edited"},
                "caseNames": {"points": ["login"]},
            },
        ),
    )
    await stages.review_stage("run", {"stage": "case_names", "action": "approve"}, "user")
    queue = await claim("third")
    await worker.complete(
        queue,
        WorkerTaskEventRequest(
            worker_id="agent",
            status="success",
            result_yaml=cases_output(),
            config_json={
                "requirementAnalysis": {"purpose": "edited"},
                "caseNames": {"points": ["login"]},
            },
        ),
    )
    reviewer = GenerationCandidateReview(repository, owned_run)
    approved = await reviewer.review("function", "run", {"action": "approve"}, "user")
    assert approved["reviewStatus"] == "approved"
    graph = await stages.generate_relation_analysis("run", {"requestId": "graph"}, "user")
    assert graph["runId"] == "run" and graph["currentStage"] == "relation_analysis"
    assert (await stages.generate_relation_analysis("run", {"requestId": "graph"}, "user"))[
        "runId"
    ] == "run"
    queue = await claim("graph")
    await worker.complete(
        queue,
        WorkerTaskEventRequest(
            worker_id="agent",
            status="success",
            config_json={
                "requirementAnalysis": {"purpose": "edited"},
                "caseNames": {"points": ["login"]},
                "caseRelations": relations_output(),
            },
        ),
    )
    final = await project_standalone_execution(session, "run")
    assert (
        final.result_yaml == cases_output()
        and final.config_json["caseRelations"] == relations_output()
    )
    attempts = db.scalars(
        select(AiGenerationAttempt).where(AiGenerationAttempt.execution_id == "run")
    ).all()
    assert len(attempts) == 6 and all(attempt.execution_id == "run" for attempt in attempts)
    assert initial.input_snapshot_json["source"]["sourceContent"] == "frozen"
    from testing_agent.services.stage_storage.relations import find_leaf

    final_attempt = next(row for row in attempts if row.output_content == cases_output())
    assert await find_leaf(session, final_attempt.id) is None


async def test_revision_request_replay_does_not_enqueue_again_or_change_inputs(db):  # noqa: F811
    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    execution, attempt, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="run",
        request_id="initial",
        actor_id="user",
        connection_id="llm",
        source={},
        config={},
        checkpoint_enabled=True,
    )
    execution.workflow_status, execution.current_stage = "waiting_review", "requirement_analysis"
    attempt.status, attempt.output_content, attempt.output_format = (
        "success",
        '{"scope":"old"}',
        "json",
    )
    attempt.review_status = "pending"
    db.scalar(select(WorkerTask).where(WorkerTask.task_id == "initial")).status = "success"
    db.commit()

    async def owned_run(user_id, run_id, kind=None, *, action="read"):
        return await project_standalone_execution(session, run_id)

    service = GenerationStageWorkflow(
        repository=AiGenerateTaskRepository(session), owned_run=owned_run
    )
    service.stage_connection = AsyncMock(return_value="llm")
    body = {
        "stage": "requirement_analysis",
        "revisionInstruction": "补全条件",
        "requestId": "revise",
        "configJson": {"requirementAnalysis": {"scope": "edited"}},
    }
    first = await service.revise_function_case_stage("run", body, "user")
    replay = await service.revise_function_case_stage("run", body, "user")
    assert first["runId"] == replay["runId"] == "run" and replay["status"] == "pending"
    with pytest.raises(AppError):
        await service.revise_function_case_stage(
            "run", {**body, "revisionInstruction": "different"}, "user"
        )
    queues = db.scalars(select(WorkerTask).where(WorkerTask.task_id == "revise")).all()
    assert len(queues) == 1
    revision = db.get(AiGenerationAttempt, queues[0].run_id)
    assert revision.revision_instruction == "补全条件"
    assert revision.input_snapshot_json["currentOutput"] == '{"scope": "edited"}'
