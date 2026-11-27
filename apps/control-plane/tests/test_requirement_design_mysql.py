"""Cross-session configuration/run races on an explicitly disposable MySQL database."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, func, select
from support.generation import generation_services
from support.mysql_initialization import async_sessions, mysql  # noqa: F401

from testing_agent.domain.api_interface import path_key
from testing_agent.models.ai_generate_task import AiGenerateTask as Task
from testing_agent.models.api_interface import ApiInterface
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.software_repository import SoftwareRepository
from testing_agent.models.sprint import Sprint
from testing_agent.models.user import User
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.deletion import delete_owned_data
from testing_agent.schemas.generation_candidates import CandidateRunRequest
from testing_agent.schemas.requirement_design import (
    RequirementDesignConfigurationRequest as Configuration,
)
from testing_agent.services.generation_dispatch_application import CandidateDispatchApplication


async def test_concurrent_default_configuration_and_same_request_run(mysql):  # noqa: F811
    engine, sessions = async_sessions(mysql)
    uid, pid, sid, rid, llm, repository_id, interface_id = [str(uuid4()) for _ in range(7)]
    request_id = uuid4()
    try:
        async with sessions() as session:
            now = datetime.now(UTC)
            session.add(User(user_id=uid, nickname="isolated-design"))
            await session.flush()
            session.add(Project(project_id=pid, user_id=uid, name="isolated-design"))
            await session.flush()
            session.add(
                SoftwareRepository(
                    software_repository_id=repository_id,
                    project_id=pid,
                    name="订单服务",
                    description="",
                    base_path="/api/v2",
                    repository_project_id="repo-1",
                    repository_group_id="group-1",
                    repository_instance_key="",
                    repository_path="commerce/order-service",
                    repository_name="order-service",
                    repository_instance_url="https://gitlab.example.com",
                    version=1,
                    created_by_user_id=uid,
                )
            )
            await session.flush()
            session.add(
                ApiInterface(
                    interface_id=interface_id,
                    software_repository_id=repository_id,
                    name="创建订单",
                    method="POST",
                    path="/orders",
                    path_key=path_key("/orders"),
                )
            )
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
                return await generation_services(
                    AiGenerateTaskRepository(session)
                ).design.configure(rid, "api", Configuration(interfaceIds=[interface_id]), uid)

        configured = await asyncio.gather(
            configure(), configure(), configure(), return_exceptions=True
        )
        assert not any(isinstance(row, BaseException) for row in configured), configured
        assert len({row["taskId"] for row in configured}) == 1

        async def start():
            async with sessions() as session:
                bundle = generation_services(AiGenerateTaskRepository(session))
                return await CandidateDispatchApplication(bundle.chain).run(
                    requirement_id=rid,
                    kind="api",
                    stage="interface_extract",
                    request=CandidateRunRequest(requestId=request_id, connectionId=llm),
                    actor_id=uid,
                )

        runs = await asyncio.gather(start(), start(), start(), return_exceptions=True)
        assert not any(isinstance(row, BaseException) for row in runs), runs
        attempt_ids = {row.attempt_id for row in runs}
        assert len(attempt_ids) == 1
        attempt_id = next(iter(attempt_ids))
        async with sessions() as session:
            assert (
                await session.scalar(
                    select(func.count()).select_from(Task).where(Task.requirement_id == rid)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(WorkerTask)
                    .where(WorkerTask.task_id == str(request_id), WorkerTask.run_id == attempt_id)
                )
                == 1
            )
    finally:
        async with sessions() as session:
            await session.execute(delete(WorkerTask).where(WorkerTask.task_id == str(request_id)))
            for task in await session.scalars(select(Task).where(Task.requirement_id == rid)):
                await delete_owned_data(session, task)
            await session.execute(
                delete(ApiInterface).where(ApiInterface.interface_id == interface_id)
            )
            await session.execute(
                delete(SoftwareRepository).where(
                    SoftwareRepository.software_repository_id == repository_id
                )
            )
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

    engine, sessions = async_sessions(mysql)
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
            tasks = generation_services(AiGenerateTaskRepository(session))
            original = tasks.access.ensure_project_access

            async def pause_before_lock(user_id, project_id, *, action="read"):
                if action == "write":
                    entered.set()
                    await proceed.wait()
                await original(user_id, project_id, action=action)

            monkeypatch.setattr(tasks.access, "ensure_project_access", pause_before_lock)
            operation = asyncio.create_task(
                tasks.design.configure(
                    rid, "api", Configuration(interfaceIds=["interface-missing"]), actor
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
