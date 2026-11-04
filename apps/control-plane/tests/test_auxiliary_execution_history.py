"""The auxiliary history projection keeps result bodies on the detail path."""

from unittest.mock import Mock

import pytest
from sqlalchemy import event, select
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db

from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.worker_task import WorkerTask
from testing_agent.schemas.ai_generate_task import (
    AiGenerateRunHistoryResponse,
    AiGenerateTaskRunResponse,
)
from testing_agent.services.auxiliary_execution import dispatch_auxiliary_execution
from testing_agent.services.auxiliary_execution_delete import delete_auxiliary_execution
from testing_agent.services.auxiliary_execution_view import auxiliary_detail, auxiliary_history
from testing_agent.services.stage_storage.worker import StageWorkerTransitions


async def test_paged_history_reads_unified_executions_without_result_bodies(db):  # noqa: F811
    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.task_type = "test_order_graph"
    db.commit()
    session = AsyncSessionAdapter(db)
    transitions = StageWorkerTransitions(session)
    for number, status in enumerate(("success", "failed", "success"), start=1):
        attempt, _ = await dispatch_auxiliary_execution(
            session,
            task=task,
            actor_id="u",
            request_id=f"worker-{number}",
            execution_id=f"execution-{number}",
            connection_id="llm",
            source={"name": f"run-{number}"},
            config={"graphInput": {"cases": [number]}},
        )
        if status == "success":
            await transitions.completed(
                attempt.stage_id,
                attempt.id,
                attempt.worker_task_id,
                content=f"result-{number}",
                output_format="text",
                output_context=None,
            )
        else:
            await transitions.failed(
                attempt.stage_id,
                attempt.id,
                attempt.worker_task_id,
                error_message="failed",
            )
        db.commit()

    listener = Mock()
    event.listen(db.bind, "before_cursor_execute", listener)
    try:
        page = await auxiliary_history(session, "task", 1, 2)
        query_count = listener.call_count
        older = await auxiliary_history(session, "task", 2, 2)
    finally:
        event.remove(db.bind, "before_cursor_execute", listener)
    assert query_count == 2
    assert page["total"] == 3 and page["statusCounts"] == {"failed": 1, "success": 2}
    assert [item["runId"] for item in page["items"]] == ["execution-3", "execution-2"]
    assert older["items"][0]["runId"] == "execution-1"
    assert older["latestRun"]["runId"] == "execution-3"
    assert page["items"][1]["errorMessage"] == "failed"
    assert "resultYaml" not in page["items"][0]
    AiGenerateRunHistoryResponse.model_validate(page)
    detail = await auxiliary_detail(session, "execution-1")
    AiGenerateTaskRunResponse.model_validate(detail)
    assert detail["resultYaml"] == "result-1"
    assert detail["snapshotJson"]["runId"] == "execution-1"
    assert detail["configJson"] == {"graphInput": {"cases": [1]}}


async def test_delete_terminal_history_preserves_previous_result_and_other_domains(db):  # noqa: F811
    from testing_agent.core.errors import AppError
    from testing_agent.models.ai_execution import AiExecution
    from testing_agent.models.ai_generation_stage import AiGenerationStage

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.task_type = "test_order_graph"
    db.commit()
    session = AsyncSessionAdapter(db)
    attempts = []
    for number in range(3):
        attempt, _ = await dispatch_auxiliary_execution(
            session,
            task=task,
            actor_id="u",
            request_id=f"delete-worker-{number}",
            execution_id=f"delete-execution-{number}",
            connection_id="llm",
            source={},
            config={},
        )
        attempts.append(attempt)
        queue = db.scalar(select(WorkerTask).where(WorkerTask.task_id == f"delete-worker-{number}"))
        if number < 2:
            await StageWorkerTransitions(session).completed(
                attempt.stage_id,
                attempt.id,
                queue.task_id,
                content=f"result-{number}",
                output_format="text",
                output_context=None,
            )
            queue.status = "success"
        db.commit()
    unrelated = WorkerTask(
        domain="api",
        task_id="delete-worker-1",
        task_type="api_case_run",
        run_id="other-domain-run",
        status="success",
    )
    db.add(unrelated)
    db.commit()
    with pytest.raises(AppError):
        await delete_auxiliary_execution(session, task_id="task", execution_id="delete-execution-2")
    stage = db.scalar(select(AiGenerationStage).where(AiGenerationStage.id == attempts[1].stage_id))
    await delete_auxiliary_execution(session, task_id="task", execution_id="delete-execution-1")
    assert db.get(AiExecution, "delete-execution-1") is None
    assert stage.current_attempt_id == attempts[0].id
    assert stage.active_attempt_id == attempts[2].id
    assert (
        db.scalar(
            select(WorkerTask).where(
                WorkerTask.domain == "api", WorkerTask.task_id == "delete-worker-1"
            )
        )
        is not None
    )
    assert (
        db.scalar(
            select(WorkerTask).where(
                WorkerTask.domain == "ai", WorkerTask.task_id == "delete-worker-1"
            )
        )
        is None
    )
    assert (await auxiliary_detail(session, "delete-execution-0"))["resultYaml"] == "result-0"
    db.rollback()
    assert db.get(AiExecution, "delete-execution-1") is not None


async def test_task_deletion_removes_attempt_queue_but_not_other_domains(db):  # noqa: F811
    from testing_agent.repositories.deletion import delete_owned_data

    seed_task(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == "task"))
    task.task_type = "test_order_graph"
    db.commit()
    session = AsyncSessionAdapter(db)
    attempt, _ = await dispatch_auxiliary_execution(
        session,
        task=task,
        actor_id="u",
        request_id="shared-queue-id",
        execution_id="execution-to-delete",
        connection_id="llm",
        source={},
        config={},
    )
    db.add(
        WorkerTask(
            domain="api",
            task_id="shared-queue-id",
            task_type="api_case_run",
            run_id=attempt.id,
            status="success",
        )
    )
    db.commit()
    await delete_owned_data(session, task)
    assert (
        db.scalar(
            select(WorkerTask).where(WorkerTask.domain == "ai", WorkerTask.run_id == attempt.id)
        )
        is None
    )
    assert (
        db.scalar(
            select(WorkerTask).where(WorkerTask.domain == "api", WorkerTask.run_id == attempt.id)
        )
        is not None
    )
