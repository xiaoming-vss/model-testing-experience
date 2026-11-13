from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter  # noqa: F401
from support.ai_execution import db as db
from support.generation import generation_services

from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.sprint import Sprint
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.worker_task import WorkerTaskRepository
from testing_agent.schemas.workers import WorkerClaimRequest, WorkerTaskEventRequest
from testing_agent.services.auxiliary_execution_view import auxiliary_detail
from testing_agent.services.worker_task import WorkerTaskService


def report_service(db):
    db.add(
        Sprint(
            sprint_id="s",
            project_id="p",
            name="Report",
            start_time=datetime(2026, 1, 1, tzinfo=UTC),
            end_time=datetime(2026, 2, 1, tzinfo=UTC),
        )
    )
    db.commit()
    repository = AiGenerateTaskRepository(AsyncSessionAdapter(db))
    metrics = SimpleNamespace(get=AsyncMock(return_value={"function": {"total": 1}}))
    return generation_services(repository, metrics)


BODY = {"sprintId": "s", "connectionId": "llm", "snapshotDate": "2026-01-15"}


async def test_direct_report_run_persists_attempt_and_can_execute_after_reload(db):
    service = report_service(db)
    result = await service.reports.run_test_report("p", BODY, "u")
    run_id = result["runId"]
    db.expunge_all()
    attempt = db.scalar(
        select(AiGenerationAttempt).where(AiGenerationAttempt.execution_id == run_id)
    )
    stage = db.get(AiGenerationStage, attempt.stage_id)
    assert stage is not None
    assert attempt.requested_by == "u"
    assert attempt.input_snapshot_json["llmConnectionId"] == "llm"
    worker = db.scalar(select(WorkerTask).where(WorkerTask.run_id == attempt.id))
    assert attempt.worker_task_id == worker.task_id
    workers = WorkerTaskService(WorkerTaskRepository(AsyncSessionAdapter(db)))
    claimed = await workers.claim("ai", WorkerClaimRequest(workerId="report-worker"))
    assert claimed["attemptId"] == attempt.id != run_id
    assert claimed["llmConnectionId"] == "llm"
    await workers.started("ai", worker.task_id, WorkerTaskEventRequest(workerId="report-worker"))
    await workers.complete(
        "ai",
        worker.task_id,
        WorkerTaskEventRequest(workerId="report-worker", status="success", resultYaml="# Report"),
    )
    db.expunge_all()
    persisted = await auxiliary_detail(service.repository.session, run_id)
    assert persisted["status"] == "success"
    assert persisted["resultYaml"] == "# Report"
    assert db.get(AiGenerationAttempt, attempt.id).status == "success"
    second = await service.reports.run_test_report("p", BODY, "u")
    assert second["taskId"] == result["taskId"]
    assert second["runId"] != run_id
    assert len(list(db.scalars(select(AiGenerationAttempt)))) == 2


async def test_report_dispatch_failure_rolls_back_task_run_attempt_and_queue(db, monkeypatch):
    from testing_agent.services import ai_report

    original_dispatch = ai_report.dispatch_auxiliary_execution

    async def failing_dispatch(*args, **kwargs):
        await original_dispatch(*args, **kwargs)
        raise RuntimeError("abort after normalized writes")

    monkeypatch.setattr(ai_report, "dispatch_auxiliary_execution", failing_dispatch)
    service = report_service(db)
    with pytest.raises(RuntimeError, match="abort after normalized writes"):
        await service.reports.run_test_report("p", BODY, "u")
    await service.repository.rollback()
    for model in (
        AiGenerateTask,
        AiExecution,
        AiGenerationStage,
        AiGenerationAttempt,
        WorkerTask,
    ):
        assert list(db.scalars(select(model))) == []


async def test_report_cannot_be_started_twice_while_its_previous_run_is_active(db):
    from testing_agent.core.errors import AppError

    service = report_service(db)
    await service.reports.run_test_report("p", BODY, "u")
    with pytest.raises(AppError):
        await service.reports.run_test_report("p", BODY, "u")
    assert len(list(db.scalars(select(AiExecution)))) == 1
