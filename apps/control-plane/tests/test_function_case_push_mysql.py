"""Run only against an explicitly configured disposable MySQL database."""

import asyncio

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql as mysql
from support.mysql_initialization import seed_row

from testing_agent.core.errors import AppError
from testing_agent.models.function_case_push import (
    FunctionCasePushOperation,
    FunctionCaseRemoteIdentity,
)
from testing_agent.models.project import Project
from testing_agent.repositories.function_case_push import FunctionCasePushRepository
from testing_agent.services.function_case_push_journal import CasePushJournal, CaseWriteIntent


@pytest.mark.asyncio
async def test_mysql_project_serialization_grants_one_remote_write_permit(mysql):
    with mysql.begin() as connection:
        project = seed_row(connection, Project.__table__)
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    first_reserved, release = asyncio.Event(), asyncio.Event()

    async def reserve(request_id, first=False):
        async with sessions() as session:
            await session.scalar(
                select(Project).where(Project.project_id == project["project_id"]).with_for_update()
            )
            journal = CasePushJournal(FunctionCasePushRepository(session))
            try:
                permit = await journal.reserve(
                    CaseWriteIntent(
                        project_id=project["project_id"],
                        case_id="concurrent-case",
                        instance_key="a" * 64,
                        actor=project["user_id"],
                        request_id=request_id,
                        target={"execution": 1},
                        payload={"title": "case"},
                    )
                )
            except AppError as exc:
                assert exc.http_code == 409
                await session.rollback()
                return False
            if first:
                first_reserved.set()
                await release.wait()
            await session.commit()
            return permit.allowed

    first = asyncio.create_task(reserve("first", True))
    second = None
    try:
        await asyncio.wait_for(first_reserved.wait(), 5)
        second = asyncio.create_task(reserve("second"))
        await asyncio.sleep(0.1)
        assert not second.done()
        release.set()
        assert await asyncio.wait_for(first, 5)
        assert not await asyncio.wait_for(second, 5)
        async with sessions() as session:
            rows = (await session.scalars(select(FunctionCasePushOperation))).all()
            assert len(rows) == 1 and rows[0].active_key is not None
    finally:
        release.set()
        for task in (first, second):
            if task is not None:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        # Explicit test evidence cleanup; the production migration refuses such destruction.
        async with sessions() as session:
            await session.execute(delete(FunctionCasePushOperation))
            await session.execute(delete(FunctionCaseRemoteIdentity))
            await session.execute(
                delete(Project).where(Project.project_id == project["project_id"])
            )
            await session.commit()
        await engine.dispose()
