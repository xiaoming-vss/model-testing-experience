"""Code-risk launches serialize on the task row in MySQL."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from support.mysql_initialization import (  # noqa: F401
    async_sessions,
    capture_statements,
    mysql,
    seed_row,
)

from testing_agent.core.errors import AppError
from testing_agent.models.ai_execution import AiExecution
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.generation_candidates import RequirementGenerationChain
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.ai_run_launcher import GenerationRunLauncher


def seed_material(connection):
    project = seed_row(connection, Project.__table__)
    sprint = seed_row(connection, Sprint.__table__, {"project_id": project["project_id"]})
    requirement = seed_row(connection, Requirement.__table__, {"sprint_id": sprint["sprint_id"]})
    source = seed_row(
        connection,
        AiGenerateTask.__table__,
        {
            "task_type": "requirement_analysis",
            "project_id": project["project_id"],
            "sprint_id": sprint["sprint_id"],
            "requirement_id": requirement["requirement_id"],
        },
    )
    seed_row(
        connection,
        RequirementGenerationChain.__table__,
        {
            "task_id": source["task_id"],
            "requirement_id": requirement["requirement_id"],
            "kind": "requirement_analysis",
        },
    )
    return {key: source[key] for key in ("project_id", "sprint_id", "requirement_id")}


def use_current_material(launcher, monkeypatch):
    monkeypatch.setattr(
        launcher, "_prepare_current_material", AsyncMock(return_value=(object(), object()))
    )
    monkeypatch.setattr(
        "testing_agent.services.ai_run_launcher.lock_prepared_requirement_root", AsyncMock()
    )
    monkeypatch.setattr("testing_agent.services.ai_run_launcher.lock_current_material", AsyncMock())


async def test_concurrent_code_risk_launch_creates_one_run(mysql, monkeypatch):  # noqa: F811
    with mysql.begin() as connection:
        material = seed_material(connection)
        task = seed_row(
            connection,
            AiGenerateTask.__table__,
            {"task_type": "code_risk_analysis", **material},
        )
    monkeypatch.setattr(
        "testing_agent.services.ai_run_launcher.require_project_access", AsyncMock()
    )
    monkeypatch.setattr(
        "testing_agent.services.ai_run_launcher.require_personal_connection", AsyncMock()
    )
    engine, sessions = async_sessions(mysql)
    statements = capture_statements(engine)

    async def dispatch():
        async with sessions() as session:
            repository = AiGenerateTaskRepository(session)
            access = SimpleNamespace(
                owned_task=AsyncMock(return_value=await repository.get_task(task["task_id"])),
                ensure_project_access=AsyncMock(),
                ensure_sprint_access=AsyncMock(),
                ensure_requirement_access=AsyncMock(),
                validate_task_scope=AsyncMock(),
            )
            launcher = GenerationRunLauncher(
                repository=repository,
                access=access,
                code_risk_analysis_service=SimpleNamespace(
                    build_snapshot=AsyncMock(
                        return_value={"requirementMaterialCurrent": {"candidateId": "current"}}
                    )
                ),
            )
            use_current_material(launcher, monkeypatch)
            try:
                return await launcher.launch(
                    "code_risk_analysis", task["task_id"], {"connectionId": "llm"}, "user"
                )
            except AppError:
                await session.rollback()
                return None

    try:
        results = await asyncio.wait_for(asyncio.gather(dispatch(), dispatch()), timeout=15)
        assert sum(result is not None for result in results) == 1
        assert not any("ai_generate_task_runs" in statement for statement in statements)
        async with sessions() as session:
            count = await session.scalar(
                sa.select(sa.func.count())
                .select_from(AiExecution)
                .where(AiExecution.task_id == task["task_id"])
            )
            assert count == 1
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(
                sa.delete(WorkerTask).where(WorkerTask.task_type == "code_risk_analysis")
            )
            connection.execute(
                sa.delete(AiGenerateTask).where(AiGenerateTask.task_id == task["task_id"])
            )


async def test_code_risk_same_request_replays_after_concurrent_dispatch(mysql, monkeypatch):  # noqa: F811
    from testing_agent.services.stage_storage import authorization

    with mysql.begin() as connection:
        material = seed_material(connection)
        task = seed_row(
            connection,
            AiGenerateTask.__table__,
            {"task_type": "code_risk_analysis", **material},
        )
    monkeypatch.setattr(
        "testing_agent.services.ai_run_launcher.require_project_access", AsyncMock()
    )
    monkeypatch.setattr(
        "testing_agent.services.ai_run_launcher.require_personal_connection", AsyncMock()
    )
    authorization_check = AsyncMock(return_value="user")
    monkeypatch.setattr(authorization, "authorize_worker_actor", authorization_check)
    snapshot = AsyncMock(return_value={"requirementMaterialCurrent": {"candidateId": "current"}})
    engine, sessions = async_sessions(mysql)
    arrived = 0
    snapshots_ready = asyncio.Event()

    async def dispatch(body, actor="user"):
        nonlocal arrived
        async with sessions() as session:
            repository = AiGenerateTaskRepository(session)
            lock_task = repository.get_task_for_update

            async def lock_after_old_snapshot(task_id):
                nonlocal arrived
                if not snapshots_ready.is_set():
                    await session.scalar(sa.select(sa.func.count()).select_from(WorkerTask))
                    arrived += 1
                    if arrived == 2:
                        snapshots_ready.set()
                    await asyncio.wait_for(snapshots_ready.wait(), timeout=5)
                return await lock_task(task_id)

            repository.get_task_for_update = lock_after_old_snapshot
            access = SimpleNamespace(
                owned_task=AsyncMock(return_value=await repository.get_task(task["task_id"])),
                ensure_project_access=AsyncMock(),
                ensure_sprint_access=AsyncMock(),
                ensure_requirement_access=AsyncMock(),
                validate_task_scope=AsyncMock(),
            )
            launcher = GenerationRunLauncher(
                repository=repository,
                access=access,
                code_risk_analysis_service=SimpleNamespace(build_snapshot=snapshot),
            )
            use_current_material(launcher, monkeypatch)
            return await launcher.launch("code_risk_analysis", task["task_id"], body, actor)

    body = {"connectionId": "llm", "requestId": "same-risk-request"}
    try:
        first, second = await asyncio.wait_for(
            asyncio.gather(dispatch(body), dispatch(body)), timeout=20
        )
        assert first["runId"] == second["runId"]
        count = snapshot.await_count
        assert (await dispatch(body))["runId"] == first["runId"]
        assert snapshot.await_count == count
        from testing_agent.core.errors import ErrForbidden

        authorization_check.side_effect = ErrForbidden()
        with pytest.raises(AppError) as rejected:
            await dispatch(body)
        assert rejected.value.http_code == 403
        authorization_check.side_effect = None
        for altered, actor in (({**body, "instruction": "changed"}, "user"), (body, "other")):
            try:
                await dispatch(altered, actor)
            except AppError as exc:
                assert exc.http_code == 400
            else:
                raise AssertionError("A request ID must not be shared across inputs or actors")
        async with sessions() as session:
            assert (
                await session.scalar(
                    sa.select(sa.func.count())
                    .select_from(AiExecution)
                    .where(AiExecution.task_id == task["task_id"])
                )
                == 1
            )
            queue = await session.scalar(
                sa.select(WorkerTask).where(WorkerTask.task_id == body["requestId"])
            )
            assert queue is not None and queue.status == "pending"
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(sa.delete(WorkerTask).where(WorkerTask.task_id == body["requestId"]))
            connection.execute(
                sa.delete(AiGenerateTask).where(AiGenerateTask.task_id == task["task_id"])
            )


@pytest.mark.parametrize("same_request", [False, True])
async def test_distinct_risks_dispatch_in_parallel_without_queue_gap_deadlock(
    mysql,  # noqa: F811
    monkeypatch,
    same_request,
):
    from testing_agent.services import auxiliary_execution

    with mysql.begin() as connection:
        materials = [seed_material(connection), seed_material(connection)]
        tasks = [
            seed_row(
                connection,
                AiGenerateTask.__table__,
                {
                    "task_type": "code_risk_analysis",
                    **material,
                },
            )
            for material in materials
        ]
    monkeypatch.setattr(
        "testing_agent.services.ai_run_launcher.require_project_access", AsyncMock()
    )
    monkeypatch.setattr(
        "testing_agent.services.ai_run_launcher.require_personal_connection", AsyncMock()
    )
    original = auxiliary_execution.dispatch_auxiliary_execution
    arrived = 0
    ready = asyncio.Event()

    async def simultaneous(*args, **kwargs):
        nonlocal arrived
        arrived += 1
        if arrived == 2:
            ready.set()
        await asyncio.wait_for(ready.wait(), timeout=5)
        return await original(*args, **kwargs)

    monkeypatch.setattr(auxiliary_execution, "dispatch_auxiliary_execution", simultaneous)
    engine, sessions = async_sessions(mysql)
    identifiers = [
        "shared-parallel-request",
        "shared-parallel-request" if same_request else "other-parallel-request",
    ]

    async def launch(task, identity):
        async with sessions() as session:
            repository = AiGenerateTaskRepository(session)
            access = SimpleNamespace(
                owned_task=AsyncMock(return_value=await repository.get_task(task["task_id"])),
                ensure_project_access=AsyncMock(),
                ensure_sprint_access=AsyncMock(),
                ensure_requirement_access=AsyncMock(),
                validate_task_scope=AsyncMock(),
            )
            launcher = GenerationRunLauncher(
                repository=repository,
                access=access,
                code_risk_analysis_service=SimpleNamespace(
                    build_snapshot=AsyncMock(
                        return_value={"requirementMaterialCurrent": {"candidateId": "current"}}
                    )
                ),
            )
            use_current_material(launcher, monkeypatch)
            try:
                return await launcher.launch(
                    "code_risk_analysis",
                    task["task_id"],
                    {"connectionId": "llm", "requestId": identity},
                    "user",
                )
            except AppError:
                await session.rollback()
                return None

    try:
        outcomes = await asyncio.wait_for(
            asyncio.gather(
                *(
                    launch(task, identity)
                    for task, identity in zip(tasks, identifiers, strict=True)
                ),
                return_exceptions=True,
            ),
            timeout=15,
        )
        assert not [item for item in outcomes if isinstance(item, BaseException)], outcomes
        assert sum(item is not None for item in outcomes) == (1 if same_request else 2)
    finally:
        await engine.dispose()
        with mysql.begin() as connection:
            connection.execute(sa.delete(WorkerTask).where(WorkerTask.task_id.in_(identifiers)))
            connection.execute(
                sa.delete(AiGenerateTask).where(
                    AiGenerateTask.task_id.in_([task["task_id"] for task in tasks])
                )
            )
