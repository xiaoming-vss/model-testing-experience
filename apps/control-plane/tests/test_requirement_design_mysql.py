"""Cross-session configuration/run races on an explicitly disposable MySQL database."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql  # noqa: F401

from testing_agent.models.ai_generate_task import AiGenerateTask as Task
from testing_agent.models.ai_generate_task import AiGenerateTaskRun as Run
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.user import User
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.schemas.requirement_design import (
    RequirementDesignConfigurationRequest as Configuration,
)
from testing_agent.schemas.requirement_design import RequirementDesignRunRequest as Start
from testing_agent.services.ai_generate_task import AiGenerateTaskService
from testing_agent.services.requirement_design import RequirementDesignService


async def test_concurrent_default_configuration_and_same_request_run(mysql):  # noqa: F811
    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    uid, pid, sid, rid, llm = [str(uuid4()) for _ in range(5)]
    try:
        async with sessions() as session:
            now = datetime.now(UTC)
            session.add(User(user_id=uid, nickname="isolated-design"))
            await session.flush()
            session.add(Project(project_id=pid, user_id=uid, name="isolated-design"))
            await session.flush()
            session.add(
                Sprint(
                    sprint_id=sid,
                    project_id=pid,
                    name="s",
                    start_time=now,
                    end_time=now + timedelta(days=1),
                )
            )
            await session.flush()
            session.add_all(
                [
                    Requirement(requirement_id=rid, sprint_id=sid, name="req"),
                    IntegrationConnection(
                        connection_id=llm,
                        project_id=pid,
                        user_id=uid,
                        provider="llm",
                        name="mine",
                        status="active",
                        secret_json={"apiKey": "isolated-only"},
                    ),
                ]
            )
            await session.commit()

        async def configure():
            async with sessions() as session:
                return await RequirementDesignService(
                    AiGenerateTaskService(AiGenerateTaskRepository(session))
                ).configure(
                    rid, "api", Configuration(sourceContent='{"openapi":"3.0.0","paths":{}}'), uid
                )

        configured = await asyncio.gather(
            configure(), configure(), configure(), return_exceptions=True
        )
        assert not any(isinstance(row, BaseException) for row in configured), configured
        assert len({row["taskId"] for row in configured}) == 1
        task_id = configured[0]["taskId"]
        request_id = uuid4()

        async def start():
            async with sessions() as session:
                return await RequirementDesignService(
                    AiGenerateTaskService(AiGenerateTaskRepository(session))
                ).start(
                    rid, "api", Start(taskId=task_id, requestId=request_id, connectionId=llm), uid
                )

        runs = await asyncio.gather(start(), start(), start(), return_exceptions=True)
        assert not any(isinstance(row, BaseException) for row in runs), runs
        assert {row["runId"] for row in runs} == {str(request_id)}
        async with sessions() as session:
            assert (
                await session.scalar(
                    select(func.count()).select_from(Task).where(Task.requirement_id == rid)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count()).select_from(Run).where(Run.task_id == task_id)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(WorkerTask)
                    .where(WorkerTask.run_id == str(request_id))
                )
                == 1
            )
    finally:
        async with sessions() as session:
            task_ids = select(Task.task_id).where(Task.requirement_id == rid)
            run_ids = select(Run.run_id).where(Run.task_id.in_(task_ids))
            await session.execute(delete(WorkerTask).where(WorkerTask.run_id.in_(run_ids)))
            await session.execute(delete(Task).where(Task.requirement_id == rid))
            await session.execute(delete(Requirement).where(Requirement.requirement_id == rid))
            await session.execute(delete(Sprint).where(Sprint.sprint_id == sid))
            await session.execute(
                delete(IntegrationConnection).where(IntegrationConnection.connection_id == llm)
            )
            await session.execute(delete(Project).where(Project.project_id == pid))
            await session.execute(delete(User).where(User.user_id == uid))
            await session.commit()
        await engine.dispose()


async def test_member_revoked_after_initial_read_cannot_save_configuration(mysql, monkeypatch):  # noqa: F811
    from testing_agent.core.errors import AppError
    from testing_agent.models.project_member import ProjectMember

    engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    owner, actor, pid, sid, rid = [str(uuid4()) for _ in range(5)]
    try:
        async with sessions() as session:
            now = datetime.now(UTC)
            session.add_all(
                [User(user_id=owner, nickname="owner"), User(user_id=actor, nickname="actor")]
            )
            await session.flush()
            session.add(Project(project_id=pid, user_id=owner, name="isolated-revocation"))
            await session.flush()
            session.add_all(
                [
                    Sprint(
                        sprint_id=sid,
                        project_id=pid,
                        name="s",
                        start_time=now,
                        end_time=now + timedelta(days=1),
                    ),
                    ProjectMember(project_id=pid, user_id=actor, role="member"),
                ]
            )
            await session.flush()
            session.add(Requirement(requirement_id=rid, sprint_id=sid, name="req"))
            await session.commit()
        entered, proceed = asyncio.Event(), asyncio.Event()
        async with sessions() as session:
            tasks = AiGenerateTaskService(AiGenerateTaskRepository(session))
            original = tasks.ensure_project_access

            async def pause_before_lock(user_id, project_id, *, action="read"):
                if action == "write":
                    entered.set()
                    await proceed.wait()
                await original(user_id, project_id, action=action)

            monkeypatch.setattr(tasks, "ensure_project_access", pause_before_lock)
            operation = asyncio.create_task(
                RequirementDesignService(tasks).configure(
                    rid, "api", Configuration(sourceContent='{"openapi":"3.0.0","paths":{}}'), actor
                )
            )
            await asyncio.wait_for(entered.wait(), 10)
            async with sessions() as revocation:
                await revocation.execute(
                    delete(ProjectMember).where(
                        ProjectMember.project_id == pid, ProjectMember.user_id == actor
                    )
                )
                await revocation.commit()
            proceed.set()
            result = (await asyncio.gather(operation, return_exceptions=True))[0]
            assert isinstance(result, AppError), result
            assert result.http_code == 403
        async with sessions() as session:
            assert (
                await session.scalar(
                    select(func.count()).select_from(Task).where(Task.requirement_id == rid)
                )
                == 0
            )
    finally:
        async with sessions() as session:
            await session.execute(delete(Task).where(Task.requirement_id == rid))
            await session.execute(delete(Requirement).where(Requirement.requirement_id == rid))
            await session.execute(delete(Sprint).where(Sprint.sprint_id == sid))
            await session.execute(delete(Project).where(Project.project_id == pid))
            await session.execute(delete(User).where(User.user_id.in_([owner, actor])))
            await session.commit()
        await engine.dispose()
