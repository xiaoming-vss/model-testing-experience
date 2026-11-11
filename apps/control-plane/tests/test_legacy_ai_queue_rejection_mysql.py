"""Old AI queue entries cannot be claimed after the execution cutover."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.core.errors import AppError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.worker_task import WorkerTaskRepository
from testing_agent.schemas.workers import (
    WorkerClaimRequest,
    WorkerProgressRequest,
    WorkerTaskEventRequest,
)
from testing_agent.services.worker_task import WorkerTaskService


async def test_legacy_ai_queue_is_rejected_without_mutation(mysql, monkeypatch):  # noqa: F811
    with mysql.begin() as connection:
        task = seed_row(connection, AiGenerateTask.__table__, {"task_type": "api_case_generate"})
        # The retired ledger no longer exists; a stale queue row references an attempt
        # that was never written, which is what post-cutover workers must reject.
        legacy_run_id = "legacy-run-without-attempt"
        queue = seed_row(
            connection,
            WorkerTask.__table__,
            {
                "domain": "ai",
                "task_type": "api_case_generate",
                "run_id": legacy_run_id,
                "status": "pending",
                "worker_id": "",
            },
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    statements = []
    sa.event.listen(
        engine.sync_engine,
        "before_cursor_execute",
        lambda _c, _u, sql, _p, _x, _m: statements.append(sql.lower()),
    )
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            service = WorkerTaskService(WorkerTaskRepository(session))
            with pytest.raises(AppError, match="AI 队列未关联有效的阶段尝试") as exc:
                await service.claim("ai", WorkerClaimRequest(worker_id="worker"))
            assert exc.value.http_code == 400
            await session.rollback()
            saved = await session.get(WorkerTask, queue["id"])
            assert saved.status == "pending" and saved.worker_id == ""
            assert saved.run_id == legacy_run_id and saved.lease_expires_at is None
            saved.status = "running"
            saved.worker_id = "worker"
            saved.lease_expires_at = datetime.now(UTC) - timedelta(minutes=1)
            await session.commit()
            event = WorkerTaskEventRequest(worker_id="worker", status="success")
            progress = WorkerProgressRequest(worker_id="worker", stage_status="waiting_review")
            for action in (
                service.snapshot("ai", queue["task_id"]),
                service.started("ai", queue["task_id"], event),
                service.heartbeat("ai", queue["task_id"], event),
                service.complete("ai", queue["task_id"], event),
                service.progress(queue["task_id"], progress),
                service.control_state("ai", queue["task_id"], "worker"),
                service.ai_worker_task(queue["task_id"]),
                service.llm_credentials(queue["task_id"]),
                service.gitlab_credentials(queue["task_id"]),
                service.requirement_document(queue["task_id"]),
            ):
                with pytest.raises(AppError) as rejected:
                    await action
                assert rejected.value.http_code == 404
            assert await service.expire_leases("ai") == 0
            from testing_agent.services import integration_lifecycle
            from testing_agent.services.worker_authorization import revoke_executions

            stage = AiGenerationStage(
                id="unified-stage",
                task_id=task["task_id"],
                stage="openapi_extract",
                active_attempt_id="unified-attempt",
            )
            session.add(stage)
            await session.flush()
            attempt = AiGenerationAttempt(
                id="unified-attempt",
                stage_id=stage.id,
                attempt_no=1,
                operation="generate",
                worker_task_id="unified-worker",
                requested_by="actor",
                status="pending",
                input_snapshot_json={"llmConnectionId": "model", "source": {}},
            )
            unified_queue = WorkerTask(
                domain="ai",
                task_id="unified-worker",
                task_type="api_case_generate",
                run_id=attempt.id,
                status="pending",
            )
            session.add_all([attempt, unified_queue])
            await session.flush()
            monkeypatch.setattr(integration_lifecycle, "revoke_integrations", AsyncMock())
            await revoke_executions(session, actor="actor", connection_id="model")
            assert attempt.status == unified_queue.status == "failed"
            assert stage.active_attempt_id is None
            await session.refresh(saved)
            assert saved.status == "running" and saved.worker_id == "worker"
            assert not any("ai_generate_task_runs" in sql for sql in statements)
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(
                sa.delete(WorkerTask).where(
                    sa.or_(WorkerTask.id == queue["id"], WorkerTask.task_id == "unified-worker")
                )
            )
            connection.execute(
                sa.delete(AiGenerateTask).where(AiGenerateTask.task_id == task["task_id"])
            )
