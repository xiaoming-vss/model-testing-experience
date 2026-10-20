"""Shared ai execution fixtures and helpers; no collected tests."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from testing_agent.db.base import Base
from testing_agent.domain.ai_execution_intent import ExecutionIntent
from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.ai_execution import graph as graph
from testing_agent.services.ai_execution import persist_run as persist_run
from testing_agent.services.ai_execution import require_current_worker


@compiles(LONGTEXT, "sqlite")
def longtext_sqlite(type_, compiler, **kw):
    return "TEXT"


def stage_by_name(stages, name):
    return next(s for s in stages if s.stage == name)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        from testing_agent.models.integration_connection import IntegrationConnection
        from testing_agent.models.project import Project
        from testing_agent.models.user import User

        session.add_all(
            [
                User(user_id="u", nickname="owner"),
                Project(project_id="p", user_id="u", name="test"),
                IntegrationConnection(
                    connection_id="llm",
                    user_id="u",
                    provider="llm",
                    name="llm",
                    project_id="p",
                    status="active",
                    secret_json={"apiKey": "test"},
                ),
            ]
        )
        for key in ("fixed-model", "original-model"):
            session.add(
                IntegrationConnection(
                    connection_id=key,
                    user_id="u",
                    provider="llm",
                    name=key,
                    project_id="p",
                    status="active",
                    secret_json={"apiKey": "test"},
                )
            )
        session.commit()
        yield session
    engine.dispose()


def create_run(db, checkpoint=True):
    from testing_agent.models.requirement import Requirement
    from testing_agent.models.sprint import Sprint

    db.add(
        Sprint(
            sprint_id="s",
            project_id="p",
            name="fixture",
            start_time=datetime(2026, 1, 1, tzinfo=UTC),
            end_time=datetime(2026, 2, 1, tzinfo=UTC),
        )
    )
    db.flush()
    db.add(Requirement(requirement_id="r", sprint_id="s", name="fixture"))
    db.flush()
    task = AiGenerateTask(
        task_id="task",
        task_type="functional_case_generate",
        name="test",
        project_id="p",
        sprint_id="s",
        requirement_id="r",
        creator_user_id="u",
        source_type="text",
        source_content="sample",
        instruction="",
    )
    run = AiGenerateTaskRun(
        run_id="run",
        task_id="task",
        project_id="p",
        sprint_id="s",
        requirement_id="r",
        trigger_user_id="u",
        status="pending",
        checkpoint_enabled=checkpoint,
        current_stage="requirement_analysis" if checkpoint else "",
        stage_status="pending",
        config_json={},
        snapshot_json={"sourceContent": "sample"},
    )
    db.add_all([task, run])
    db.flush()
    worker = enqueue(db, run, "w1")
    return run, worker


def enqueue(db, run, key, operation=None, *, connection_id="llm", intent=None):
    task = WorkerTask(
        domain="ai",
        task_id=key,
        task_type="functional_case_generate",
        run_id=run.run_id,
        status="pending",
    )
    db.add(task)
    run.status = "pending"
    persist_run(
        db,
        run,
        intent=replace(
            intent or ExecutionIntent(operation=operation), llm_connection_id=connection_id
        ),
        worker=task,
    )
    db.commit()
    return task


def event(db, run, worker, *, status, stage, config=None, output=None):
    require_current_worker(db, run, worker)
    run.current_stage = stage
    run.status = status
    run.stage_status = "waiting_review" if status == "waiting_review" else "running"
    worker.status = "success" if status in {"success", "waiting_review"} else status
    if config is not None:
        run.config_json = config
    if output is not None:
        run.result_yaml = output
    persist_run(db, run, intent=ExecutionIntent(worker_event_id=worker.task_id), worker=worker)
    db.commit()


class AsyncSessionAdapter:
    """Use the real repositories/services against SQLite without an async driver."""

    def __init__(self, session):
        self.sync = session

    async def run_sync(self, fn):
        return fn(self.sync)

    async def execute(self, stmt):
        return self.sync.execute(stmt)

    async def scalar(self, stmt):
        return self.sync.scalar(stmt)

    async def scalars(self, stmt):
        return self.sync.scalars(stmt)

    async def commit(self):
        self.sync.commit()

    async def delete(self, row):
        self.sync.delete(row)

    async def flush(self):
        self.sync.flush()

    async def refresh(self, row):
        self.sync.refresh(row)

    async def rollback(self):
        self.sync.rollback()

    def add(self, row):
        self.sync.add(row)

    def add_all(self, rows):
        self.sync.add_all(rows)
