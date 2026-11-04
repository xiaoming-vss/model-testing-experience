"""Shared production-model fixtures and helpers; no collected tests."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from testing_agent.db.base import Base
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.user import User


@compiles(LONGTEXT, "sqlite")
def longtext_sqlite(type_, compiler, **kw):
    return "TEXT"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
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


def seed_task(
    db,
    *,
    task_id="task",
    task_type="functional_case_generate",
    requirement_id="r",
    source_content="sample",
):
    """Create the requirement/task records shared by independent execution tests."""
    if db.get(Sprint, "s") is None:
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
    if requirement_id and db.get(Requirement, requirement_id) is None:
        db.add(Requirement(requirement_id=requirement_id, sprint_id="s", name="fixture"))
        db.flush()
    task = AiGenerateTask(
        task_id=task_id,
        task_type=task_type,
        name="test",
        project_id="p",
        sprint_id="s",
        requirement_id=requirement_id,
        creator_user_id="u",
        source_type="text",
        source_content=source_content,
        instruction="",
    )
    db.add(task)
    db.commit()
    return task


class AsyncSessionAdapter:
    """Use the real repositories/services against SQLite without an async driver."""

    def __init__(self, session):
        self.sync = session

    @asynccontextmanager
    async def begin_nested(self):
        with self.sync.begin_nested():
            yield

    async def run_sync(self, fn):
        return fn(self.sync)

    async def execute(self, stmt):
        return self.sync.execute(stmt)

    async def scalar(self, stmt):
        return self.sync.scalar(stmt)

    async def get(self, entity, key):
        return self.sync.get(entity, key)

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
