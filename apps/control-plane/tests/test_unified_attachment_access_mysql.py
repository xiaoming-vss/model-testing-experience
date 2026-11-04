"""Revision file ownership resolves both unified identity forms without the old ledger."""

from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.core.errors import AppError
from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.services.stored_file_access import require_file_resource


async def test_revision_file_ownership_uses_attempts_and_execution(mysql):  # noqa: F811
    with mysql.begin() as connection:
        task = seed_row(
            connection, AiGenerateTask.__table__, {"task_type": "functional_case_generate"}
        )
        stage = seed_row(connection, AiGenerationStage.__table__, {"task_id": task["task_id"]})
        execution = seed_row(
            connection,
            AiExecution.__table__,
            {"task_id": task["task_id"], "workflow_status": "failed"},
        )
        first = seed_row(
            connection,
            AiGenerationAttempt.__table__,
            {
                "stage_id": stage["id"],
                "execution_id": execution["execution_id"],
                "attempt_no": 1,
                "input_snapshot_json": {"config": {"revisionAttachments": [{"fileId": "first"}]}},
            },
        )
        second = seed_row(
            connection,
            AiGenerationAttempt.__table__,
            {
                "stage_id": stage["id"],
                "execution_id": execution["execution_id"],
                "attempt_no": 2,
                "input_snapshot_json": {"config": {"revisionAttachments": [{"fileId": "second"}]}},
            },
        )
        other_task = seed_row(
            connection,
            AiGenerateTask.__table__,
            {"task_type": "functional_case_generate", "project_id": task["project_id"]},
        )
        other_execution = seed_row(
            connection, AiExecution.__table__, {"task_id": other_task["task_id"]}
        )
        seed_row(
            connection,
            AiGenerationAttempt.__table__,
            {
                "stage_id": stage["id"],
                "execution_id": other_execution["execution_id"],
                "attempt_no": 3,
                "input_snapshot_json": {"config": {"revisionAttachments": [{"fileId": "forged"}]}},
            },
        )
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sql = []
    sa.event.listen(
        engine.sync_engine,
        "before_cursor_execute",
        lambda _c, _u, s, _p, _x, _m: sql.append(s.lower()),
    )
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:

            def file(resource_id, file_id, project_id=task["project_id"]):
                return SimpleNamespace(
                    status="attached",
                    resource_type="ai_generate_run",
                    purpose="attachment",
                    resource_id=resource_id,
                    file_id=file_id,
                    project_id=project_id,
                )

            await require_file_resource(session, file(first["id"], "first"))
            await require_file_resource(session, file(execution["execution_id"], "first"))
            await require_file_resource(session, file(execution["execution_id"], "second"))
            for row in (
                file(first["id"], "second"),
                file(second["id"], "first"),
                file(execution["execution_id"], "missing"),
                file(execution["execution_id"], "first", "other-project"),
                file(other_execution["execution_id"], "forged"),
                file("old-run", "first"),
            ):
                with pytest.raises(AppError) as rejected:
                    await require_file_resource(session, row)
                assert rejected.value.http_code == 404
            assert not any("ai_generate_task_runs" in statement for statement in sql)
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(sa.delete(AiGenerationStage))
            connection.execute(
                sa.delete(AiGenerateTask).where(
                    AiGenerateTask.task_id.in_([task["task_id"], other_task["task_id"]])
                )
            )
