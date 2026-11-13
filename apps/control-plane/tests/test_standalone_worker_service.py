"""Independent Worker leases and authority remain bound to one execution."""

import json
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db
from support.requirement_versions import material_artifact, points_artifact, scope_artifact

from testing_agent.core.errors import AppError, ErrForbidden
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.worker_task import WorkerTask
from testing_agent.schemas.workers import WorkerClaimRequest, WorkerTaskEventRequest
from testing_agent.services import standalone_worker_authorization as auth
from testing_agent.services.standalone_execution import start_standalone_execution
from testing_agent.services.standalone_worker_service import StandaloneWorkerService

SOURCE = {"sourceContent": json.dumps(material_artifact(), ensure_ascii=False)}
SCOPE = scope_artifact()
POINTS = points_artifact()


async def test_worker_lease_and_revocation_update_only_active_execution(db, monkeypatch):  # noqa: F811
    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    execution, attempt, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="run",
        request_id="worker",
        actor_id="user",
        connection_id="llm",
        source={},
        config={},
        checkpoint_enabled=True,
    )
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "worker"))
    monkeypatch.setattr(auth, "authorize_worker_actor", AsyncMock(return_value="user"))
    service = StandaloneWorkerService(session)
    assert await service.is_standalone(queue)
    claim = await service.claim(queue, WorkerClaimRequest(worker_id="agent"))
    assert claim["attemptId"] == attempt.id and execution.workflow_status == "claimed"
    assert (await service.snapshot(queue))["run"]["attemptId"] == attempt.id
    with pytest.raises(AppError):
        await service.started(queue, WorkerTaskEventRequest(worker_id="wrong", run_id=attempt.id))
    await service.started(queue, WorkerTaskEventRequest(worker_id="agent", run_id=attempt.id))
    assert execution.workflow_status == attempt.status == queue.status == "running"
    await service.heartbeat(queue, WorkerTaskEventRequest(worker_id="agent", run_id=attempt.id))
    assert queue.lease_expires_at is not None
    monkeypatch.setattr(auth, "authorize_worker_actor", AsyncMock(side_effect=ErrForbidden()))
    with pytest.raises(type(ErrForbidden)):
        await service.heartbeat(queue, WorkerTaskEventRequest(worker_id="agent", run_id=attempt.id))
    assert execution.workflow_status == attempt.status == queue.status == "failed"
    assert attempt.error_message and execution.finished_at is not None


async def test_continuous_callbacks_save_stage_artifacts_and_final_result(db, monkeypatch):  # noqa: F811
    from support.direct_graph import cases_output, relations_output

    from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
    from testing_agent.schemas.workers import WorkerProgressRequest
    from testing_agent.services.standalone_execution_view import project_standalone_execution

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    execution, first, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="continuous",
        request_id="worker",
        actor_id="user",
        connection_id="llm",
        source=SOURCE,
        config={},
        checkpoint_enabled=False,
    )
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "worker"))
    monkeypatch.setattr(auth, "authorize_worker_actor", AsyncMock(return_value="user"))
    service = StandaloneWorkerService(session)
    await service.claim(queue, WorkerClaimRequest(worker_id="agent"))
    await service.started(queue, WorkerTaskEventRequest(worker_id="agent"))

    def progress(stage, config):
        return WorkerProgressRequest(
            worker_id="agent",
            task_id="worker",
            run_id=first.id,
            current_stage=stage,
            stage_status="running",
            config_json=config,
        )

    await service.progress(
        queue,
        progress(
            "requirement_analysis",
            {
                "requirementAnalysis": SCOPE,
                "caseNames": None,
            },
        ),
    )
    await service.progress(
        queue,
        progress(
            "case_names",
            {
                "requirementAnalysis": SCOPE,
                "caseNames": POINTS,
            },
        ),
    )
    # Lost acknowledgements may replay an earlier event, without moving backward.
    await service.progress(queue, progress("requirement_analysis", {"requirementAnalysis": SCOPE}))
    assert execution.current_stage == "case_names"
    with pytest.raises(AppError):
        await service.progress(
            queue,
            progress("requirement_analysis", {"requirementAnalysis": {"purpose": "tampered"}}),
        )
    with pytest.raises(AppError):
        await service.progress(
            queue,
            progress(
                "case_names",
                {
                    "requirementAnalysis": {"purpose": "tampered"},
                    "caseNames": POINTS,
                },
            ),
        )
    await service.progress(queue, progress("detailed_cases", {}))
    body = WorkerTaskEventRequest(
        worker_id="agent",
        run_id=first.id,
        status="success",
        result_yaml=cases_output(),
        config_json={
            "requirementAnalysis": SCOPE,
            "caseNames": POINTS,
        },
    )
    await service.complete(queue, body)
    projection = await project_standalone_execution(session, execution.execution_id)
    assert queue.status == execution.workflow_status == "success"
    assert projection.result_yaml == cases_output()
    assert projection.config_json["requirementAnalysis"] == SCOPE
    assert projection.config_json["caseNames"] == POINTS
    attempts = db.scalars(
        select(AiGenerationAttempt).where(
            AiGenerationAttempt.execution_id == execution.execution_id
        )
    ).all()
    assert len(attempts) == 3 and all(attempt.status == "success" for attempt in attempts)
    with pytest.raises(AppError):
        await service.complete(queue, body)

    from testing_agent.models.ai_generation_stage import AiGenerationStage
    from testing_agent.services.standalone_candidate import review_standalone_candidate
    from testing_agent.services.standalone_dispatch import enqueue_standalone_attempt

    final = db.scalar(
        select(AiGenerationAttempt)
        .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
        .where(
            AiGenerationAttempt.execution_id == execution.execution_id,
            AiGenerationStage.stage == "detailed_cases",
        )
    )
    await review_standalone_candidate(
        session,
        task=task,
        execution_id=execution.execution_id,
        stage_name="detailed_cases",
        expected_attempt_id=final.id,
        actor_id="reviewer",
        approved=True,
        comment="ok",
    )
    graph, _ = await enqueue_standalone_attempt(
        session,
        task=task,
        execution_id=execution.execution_id,
        request_id="graph-worker",
        actor_id="user",
        connection_id="llm",
        stage_name="relation_analysis",
        operation="advance",
        expected_attempt_id=final.id,
        config={},
    )
    graph_queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "graph-worker"))
    claim = await service.claim(graph_queue, WorkerClaimRequest(worker_id="agent"))
    assert claim["currentStage"] == "relation_analysis"
    await service.started(graph_queue, WorkerTaskEventRequest(worker_id="agent"))
    await service.complete(
        graph_queue,
        WorkerTaskEventRequest(
            worker_id="agent",
            run_id=graph.id,
            status="success",
            config_json={
                "requirementAnalysis": SCOPE,
                "caseNames": POINTS,
                "caseRelations": relations_output(),
            },
        ),
    )
    result = await project_standalone_execution(session, execution.execution_id)
    assert (
        result.result_yaml == cases_output()
        and result.config_json["caseRelations"] == relations_output()
    )


async def test_checkpoint_requires_current_stage_and_stops_for_review(db, monkeypatch):  # noqa: F811
    from testing_agent.schemas.workers import WorkerProgressRequest

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    execution, attempt, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="checkpoint",
        request_id="worker",
        actor_id="user",
        connection_id="llm",
        source=SOURCE,
        config={},
        checkpoint_enabled=True,
    )
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "worker"))
    monkeypatch.setattr(auth, "authorize_worker_actor", AsyncMock(return_value="user"))
    service = StandaloneWorkerService(session)
    await service.claim(queue, WorkerClaimRequest(worker_id="agent"))
    await service.started(queue, WorkerTaskEventRequest(worker_id="agent"))
    with pytest.raises(AppError):
        await service.progress(
            queue,
            WorkerProgressRequest(
                worker_id="agent",
                current_stage="case_names",
                stage_status="waiting_review",
                config_json={"caseNames": {"points": ["x"]}},
            ),
        )
    assert queue.status == execution.workflow_status == "running"
    await service.progress(
        queue,
        WorkerProgressRequest(
            worker_id="agent",
            current_stage="requirement_analysis",
            stage_status="waiting_review",
            config_json={"requirementAnalysis": SCOPE},
        ),
    )
    assert queue.status == "success" and execution.workflow_status == "waiting_review"
    assert attempt.status == "success" and attempt.review_status == "pending"


@pytest.mark.parametrize("kind", ["api", "ui"])
async def test_api_and_ui_checkpoints_validate_worker_artifact(db, monkeypatch, kind):  # noqa: F811
    from support.ui_generation_fixtures import read

    from testing_agent.schemas.workers import WorkerProgressRequest

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    task.task_type = "api_case_generate" if kind == "api" else "ui_case_generate"
    db.commit()
    session = AsyncSessionAdapter(db)
    source = (
        {"apiWorkflowVersion": "api_two_stage/1.0"}
        if kind == "api"
        else {"uiWorkflowVersion": "ui_three_stage/1.0", "functionalCases": read("cases")}
    )
    execution, attempt, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="run",
        request_id="worker",
        actor_id="user",
        connection_id="llm",
        source=source,
        config={},
        checkpoint_enabled=True,
    )
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "worker"))
    monkeypatch.setattr(auth, "authorize_worker_actor", AsyncMock(return_value="user"))
    service = StandaloneWorkerService(session)
    claim = await service.claim(queue, WorkerClaimRequest(worker_id="agent"))
    stage, field, artifact = (
        ("openapi_extract", "apiExtraction", {"test": {"path": "/x", "method": "GET"}})
        if kind == "api"
        else ("ui_surface", "uiSurface", read("surface"))
    )
    assert claim["currentStage"] == stage and claim["checkpointEnabled"] is True
    await service.started(queue, WorkerTaskEventRequest(worker_id="agent"))
    with pytest.raises(AppError):
        await service.progress(
            queue,
            WorkerProgressRequest(
                worker_id="agent",
                current_stage=stage,
                stage_status="waiting_review",
                config_json={field: {}},
            ),
        )
    assert execution.workflow_status == "running"
    await service.progress(
        queue,
        WorkerProgressRequest(
            worker_id="agent",
            current_stage=stage,
            stage_status="waiting_review",
            config_json={field: artifact},
        ),
    )
    assert attempt.status == "success" and execution.workflow_status == "waiting_review"


async def test_worker_service_routes_independent_run_through_current_protocol(db, monkeypatch):  # noqa: F811
    from support.direct_graph import cases_output

    from testing_agent.repositories.worker_task import WorkerTaskRepository
    from testing_agent.schemas.workers import WorkerProgressRequest
    from testing_agent.services.standalone_execution_view import project_standalone_execution
    from testing_agent.services.worker_task import WorkerTaskService

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    execution, attempt, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="public-run",
        request_id="worker",
        actor_id="user",
        connection_id="llm",
        source=SOURCE,
        config={},
        checkpoint_enabled=False,
    )
    db.commit()
    monkeypatch.setattr(auth, "authorize_worker_actor", AsyncMock(return_value="user"))
    service = WorkerTaskService(WorkerTaskRepository(session))
    claim = await service.claim("ai", WorkerClaimRequest(worker_id="agent"))
    assert claim["attemptId"] == attempt.id and claim["checkpointEnabled"] is False
    snapshot = await service.snapshot("ai", "worker")
    assert snapshot["run"]["attemptId"] == attempt.id
    await service.started("ai", "worker", WorkerTaskEventRequest(worker_id="agent"))
    assert await service.control_state("ai", "worker", "agent") == {"stopRequested": False}
    await service.progress(
        "worker",
        WorkerProgressRequest(
            worker_id="agent",
            run_id=attempt.id,
            current_stage="case_names",
            stage_status="running",
            config_json={"requirementAnalysis": SCOPE, "caseNames": POINTS},
        ),
    )
    result = await service.complete(
        "ai",
        "worker",
        WorkerTaskEventRequest(
            worker_id="agent",
            run_id=attempt.id,
            status="success",
            result_yaml=cases_output(),
            config_json={"requirementAnalysis": SCOPE, "caseNames": POINTS},
        ),
    )
    assert result["status"] == "success"
    projection = await project_standalone_execution(session, execution.execution_id)
    assert projection.result_yaml == cases_output() and projection.run_id == "public-run"


async def test_expired_worker_lease_fails_only_its_current_execution(db, monkeypatch):  # noqa: F811
    from datetime import UTC, datetime, timedelta

    from testing_agent.repositories.worker_task import WorkerTaskRepository
    from testing_agent.services.worker_task import WorkerTaskService

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    execution, attempt, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="lease",
        request_id="worker",
        actor_id="user",
        connection_id="llm",
        source={},
        config={},
        checkpoint_enabled=True,
    )
    db.commit()
    monkeypatch.setattr(auth, "authorize_worker_actor", AsyncMock(return_value="user"))
    service = WorkerTaskService(WorkerTaskRepository(session))
    await service.claim("ai", WorkerClaimRequest(worker_id="agent"))
    await service.started("ai", "worker", WorkerTaskEventRequest(worker_id="agent"))
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "worker"))
    queue.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    # More retired rows than the discovery window must not starve the valid lease.
    db.add_all(
        WorkerTask(
            domain="ai",
            task_id=f"legacy-{number}",
            task_type="functional_case_generate",
            run_id=f"old-run-{number}",
            status="running",
            worker_id="old-agent",
            lease_expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        for number in range(501)
    )
    db.commit()
    assert await service.expire_leases("ai") == 1
    assert queue.status == execution.workflow_status == attempt.status == "failed"
    assert "超时" in attempt.error_message
    with pytest.raises(AppError):
        await service.complete(
            "ai",
            "worker",
            WorkerTaskEventRequest(
                worker_id="agent",
                run_id=attempt.id,
                status="success",
                result_yaml="late",
            ),
        )


async def test_revocation_retires_only_the_matching_standalone_actor(db, monkeypatch):  # noqa: F811
    from testing_agent.services import integration_lifecycle
    from testing_agent.services.worker_authorization import revoke_executions

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.requirement_id = ""
    db.commit()
    session = AsyncSessionAdapter(db)
    first, first_attempt, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="first",
        request_id="worker-first",
        actor_id="first-user",
        connection_id="llm",
        source={},
        config={},
        checkpoint_enabled=True,
    )
    second, second_attempt, _ = await start_standalone_execution(
        session,
        task=task,
        execution_id="second",
        request_id="worker-second",
        actor_id="other-user",
        connection_id="llm",
        source={},
        config={},
        checkpoint_enabled=True,
    )
    db.commit()
    monkeypatch.setattr(integration_lifecycle, "revoke_integrations", AsyncMock())
    await revoke_executions(session, actor="first-user")
    assert first.workflow_status == first_attempt.status == "failed"
    assert second.workflow_status == second_attempt.status == "pending"
    queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == "worker-first"))
    assert queue.status == "failed" and "授权" in first_attempt.error_message
