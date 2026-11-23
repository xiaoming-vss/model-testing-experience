"""Independent candidate chains must be able to dispatch concurrently."""

import asyncio
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.domain.generation_root_fingerprints import fingerprint_root_input
from testing_agent.models import Base
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.worker_task import WorkerTask
from testing_agent.schemas.generation_candidates import CandidateRunRequest
from testing_agent.services import generation_candidate_dispatch as dispatch


def test_independent_candidate_chains_dispatch_in_parallel(mysql, monkeypatch):  # noqa: F811
    tables = Base.metadata.tables
    with mysql.begin() as conn:
        project = seed_row(conn, tables["projects"])
        sprint = seed_row(conn, tables["sprints"], {"project_id": project["project_id"]})
        tasks = []
        for _ in range(2):
            requirement = seed_row(conn, tables["requirements"], {"sprint_id": sprint["sprint_id"]})
            task = seed_row(
                conn,
                tables["ai_generate_tasks"],
                {
                    "project_id": project["project_id"],
                    "sprint_id": sprint["sprint_id"],
                    "requirement_id": requirement["requirement_id"],
                    "task_type": "requirement_analysis",
                },
            )
            seed_row(
                conn,
                tables["requirement_generation_chains"],
                {
                    "requirement_id": requirement["requirement_id"],
                    "kind": "requirement_analysis",
                    "task_id": task["task_id"],
                },
            )
            seed_row(
                conn,
                tables["ai_generation_stages"],
                {
                    "task_id": task["task_id"],
                    "stage": "extracting_text",
                },
            )
            tasks.append(task)

    async def exercise():
        engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        original = dispatch.reserve_worker_identity
        arrived = 0
        ready = asyncio.Event()

        async def simultaneous(*args, **kwargs):
            nonlocal arrived
            arrived += 1
            if arrived == 2:
                ready.set()
            await asyncio.wait_for(ready.wait(), timeout=5)
            return await original(*args, **kwargs)

        monkeypatch.setattr(dispatch, "reserve_worker_identity", simultaneous)

        async def start(task_data):
            source = {
                "requirementId": task_data["requirement_id"],
                "documentFileId": "file",
                "documentHash": "hash",
                "documentType": "docx",
                "documentFilename": "requirement.docx",
                "documentDownloadUrl": "/internal/document",
                "sourceContent": "/internal/document",
                "workflowVersion": 2,
            }
            root = fingerprint_root_input("requirement_document", source)
            async with sessions() as session:
                task = await session.scalar(
                    sa.select(AiGenerateTask)
                    .where(AiGenerateTask.task_id == task_data["task_id"])
                    .with_for_update()
                )
                request = CandidateRunRequest(connection_id="llm", request_id=uuid4())
                result = await dispatch.dispatch_candidate_stage(
                    session,
                    task=task,
                    kind="requirement_analysis",
                    stage="extracting_text",
                    request=request,
                    actor_id="actor",
                    source=source,
                    direct_roots=(root,),
                    current_root_hashes={root.key: root.content_hash},
                )
                await session.commit()
                return result.attempt.id

        try:
            outcomes = await asyncio.wait_for(asyncio.gather(*(start(task) for task in tasks)), 15)
            assert len(set(outcomes)) == 2
            async with sessions() as session:
                assert await session.scalar(sa.select(sa.func.count()).select_from(WorkerTask)) == 2
        finally:
            await engine.dispose()

    asyncio.run(exercise())
