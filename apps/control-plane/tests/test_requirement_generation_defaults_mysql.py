"""Real MySQL persists the default generation rows created with a requirement."""

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.models import Base
from testing_agent.models.generation_candidates import (
    AiGenerationStageContent,
    RequirementGenerationChain,
)
from testing_agent.models.requirement import Requirement
from testing_agent.services.requirement_generation_defaults import add_default_generation_tasks


def test_requirement_creation_persists_chains_and_empty_stage_content(mysql):  # noqa: F811
    tables = Base.metadata.tables
    with mysql.begin() as conn:
        project = seed_row(conn, tables["projects"])
        sprint = seed_row(conn, tables["sprints"], {"project_id": project["project_id"]})

    async def exercise():
        engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                requirement = Requirement(
                    requirement_id="req-default-generation",
                    sprint_id=sprint["sprint_id"],
                    name="default generation",
                    document_type="word",
                    document_content="",
                )
                session.add(requirement)
                await add_default_generation_tasks(
                    session, requirement, project["project_id"], project["user_id"]
                )
                await session.commit()

            async with factory() as session:
                chains = list(
                    await session.scalars(
                        sa.select(RequirementGenerationChain).where(
                            RequirementGenerationChain.requirement_id == "req-default-generation"
                        )
                    )
                )
                assert {chain.kind for chain in chains} == {"requirement_analysis", "function"}
                contents = list(
                    await session.scalars(
                        sa.select(AiGenerationStageContent).where(
                            AiGenerationStageContent.chain_id.in_(
                                [chain.chain_id for chain in chains]
                            )
                        )
                    )
                )
                assert len(contents) == 7
                assert {content.chain_id for content in contents} == {
                    chain.chain_id for chain in chains
                }
                assert all(content.content is None for content in contents)
        finally:
            await engine.dispose()

    asyncio.run(exercise())
