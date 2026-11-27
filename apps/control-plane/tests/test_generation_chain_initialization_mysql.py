"""Real MySQL serializes first-time candidate chain initialization."""

import asyncio

import sqlalchemy as sa
from support.generation import generation_services
from support.mysql_initialization import async_sessions, mysql, seed_row  # noqa: F401

from testing_agent.models import Base
from testing_agent.models.generation_candidates import (
    AiGenerationStageContent,
    RequirementGenerationChain,
)
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.generation_chain_initialization import CandidateChainInitialization


def test_concurrent_fresh_initialization_produces_one_chain(mysql):  # noqa: F811
    tables = Base.metadata.tables
    with mysql.begin() as conn:
        project = seed_row(conn, tables["projects"])
        sprint = seed_row(conn, tables["sprints"], {"project_id": project["project_id"]})
        seed_row(
            conn,
            tables["requirements"],
            {"requirement_id": "req", "sprint_id": sprint["sprint_id"]},
        )
        task = seed_row(
            conn,
            tables["ai_generate_tasks"],
            {
                "project_id": project["project_id"],
                "sprint_id": sprint["sprint_id"],
                "requirement_id": "req",
                "task_type": "functional_case_generate",
            },
        )

    async def exercise():
        engine, factory = async_sessions(mysql)

        async def initialize():
            async with factory() as session:
                app = CandidateChainInitialization(
                    generation_services(AiGenerateTaskRepository(session)).chain
                )
                return await app.initialize(
                    requirement_id="req",
                    kind="function",
                    task_id=task["task_id"],
                    actor_id=project["user_id"],
                )

        try:
            first, second = await asyncio.gather(initialize(), initialize())
            assert first.chain_id == second.chain_id
            assert sorted((first.created, second.created)) == [False, True]
            async with factory() as session:
                assert (
                    await session.scalar(
                        sa.select(sa.func.count()).select_from(RequirementGenerationChain)
                    )
                    == 1
                )
                assert (
                    await session.scalar(
                        sa.select(sa.func.count()).select_from(AiGenerationStageContent)
                    )
                    == 3
                )
        finally:
            await engine.dispose()

    asyncio.run(exercise())
