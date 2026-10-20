from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db
from support.generation import generation_services

from testing_agent.models.ai_generate_execution import AiGenerateRunStage, AiGenerateStageAttempt
from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
from testing_agent.models.sprint import Sprint
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.worker_task import WorkerTaskRepository
from testing_agent.schemas.workers import WorkerClaimRequest, WorkerTaskEventRequest
from testing_agent.services.ai_execution.writer import SqlExecutionWriter
from testing_agent.services.worker_task import WorkerTaskService


def report_service(db, writer=None):
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
    return generation_services(repository, metrics, execution_writer=writer)


BODY = {"sprintId": "s", "connectionId": "llm", "snapshotDate": "2026-01-15"}


async def test_direct_report_run_persists_attempt_and_can_execute_after_reload(db):
    service = report_service(db)
    result = await service.reports.run_test_report("p", BODY, "u")
    run_id = result["runId"]
    db.expunge_all()
    stage = db.scalar(select(AiGenerateRunStage).where(AiGenerateRunStage.run_id == run_id))
    assert stage is not None
    attempt = db.get(AiGenerateStageAttempt, stage.active_attempt_id)
    assert attempt.requested_by == "u"
    assert attempt.input_snapshot_json["llmConnectionId"] == "llm"
    worker = db.scalar(select(WorkerTask).where(WorkerTask.run_id == run_id))
    assert attempt.worker_task_id == worker.task_id
    workers = WorkerTaskService(WorkerTaskRepository(AsyncSessionAdapter(db)))
    claimed = await workers.claim("ai", WorkerClaimRequest(workerId="report-worker"))
    assert claimed["runId"] == run_id
    assert claimed["llmConnectionId"] == "llm"
    await workers.started("ai", worker.task_id, WorkerTaskEventRequest(workerId="report-worker"))
    await workers.complete(
        "ai",
        worker.task_id,
        WorkerTaskEventRequest(workerId="report-worker", status="success", resultYaml="# Report"),
    )
    db.expunge_all()
    persisted = await service.repository.get_run(run_id)
    assert persisted.status == "success"
    assert persisted.result_yaml == "# Report"
    assert db.get(AiGenerateStageAttempt, attempt.id).status == "success"
    second = await service.reports.run_test_report("p", BODY, "u")
    assert second["taskId"] == result["taskId"]
    assert second["runId"] != run_id
    assert len(list(db.scalars(select(AiGenerateStageAttempt)))) == 2


async def test_report_writer_failure_rolls_back_task_run_attempt_and_queue(db):
    class FailingWriter(SqlExecutionWriter):
        async def save(self, session, run, **kwargs):
            await super().save(session, run, **kwargs)
            raise RuntimeError("abort after normalized writes")

    service = report_service(db, FailingWriter())
    with pytest.raises(RuntimeError, match="abort after normalized writes"):
        await service.reports.run_test_report("p", BODY, "u")
    await service.repository.rollback()
    for model in (
        AiGenerateTask,
        AiGenerateTaskRun,
        AiGenerateRunStage,
        AiGenerateStageAttempt,
        WorkerTask,
    ):
        assert list(db.scalars(select(model))) == []
