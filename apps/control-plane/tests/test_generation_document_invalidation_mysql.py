"""Changing a requirement document invalidates dependent slots atomically in MySQL."""

import asyncio
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.models import Base
from testing_agent.models.generation_candidates import AiGenerationStageContent
from testing_agent.repositories.requirement import RequirementRepository
from testing_agent.schemas.requirement import UpdateRequirementRequest
from testing_agent.services.requirement import RequirementService


def test_document_update_rotates_mysql_current_token(mysql):  # noqa: F811
    tables = Base.metadata.tables
    with mysql.begin() as conn:
        project = seed_row(conn, tables["projects"])
        sprint = seed_row(conn, tables["sprints"], {"project_id": project["project_id"]})
        requirement = seed_row(
            conn,
            tables["requirements"],
            {
                "sprint_id": sprint["sprint_id"],
                "document_type": "docx",
                "document_file_id": "old",
                "document_filename": "old.docx",
                "document_hash": "old-hash",
            },
        )
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
        chain = seed_row(
            conn,
            tables["requirement_generation_chains"],
            {
                "requirement_id": requirement["requirement_id"],
                "task_id": task["task_id"],
                "kind": "requirement_analysis",
            },
        )
        stage = seed_row(
            conn,
            tables["ai_generation_stages"],
            {"task_id": task["task_id"], "stage": "extracting_text"},
        )
        candidate = seed_row(
            conn,
            tables["ai_generation_candidates"],
            {
                "chain_id": chain["chain_id"],
                "stage_id": stage["id"],
                "content": "retained body",
                "disposition": "available",
                "generation_mode": "current",
            },
        )
        seed_row(
            conn,
            tables["ai_generation_stage_contents"],
            {
                "stage_id": stage["id"],
                "chain_id": chain["chain_id"],
                "stage": "extracting_text",
                "source_candidate_id": candidate["candidate_id"],
                "content": "retained body",
                "content_token": "old-token",
            },
        )

    class SprintAccess:
        async def get_accessible_entity(self, user_id, sprint_id, *, action="read"):
            return SimpleNamespace(sprint_id=sprint_id, project_id=project["project_id"])

    class Files:
        async def attach(
            self, user_id, file_id, project_id, resource_type, resource_id, *, purpose
        ):
            return SimpleNamespace(file_id=file_id, filename="new.docx", sha256="new-hash")

    async def exercise():
        engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                service = RequirementService(
                    RequirementRepository(session), SprintAccess(), files=Files()
                )
                await service.update(
                    "user",
                    requirement["requirement_id"],
                    UpdateRequirementRequest(documentFileId="new"),
                )
            async with factory() as session:
                slot = await session.scalar(
                    select(AiGenerationStageContent).where(
                        AiGenerationStageContent.stage_id == stage["id"]
                    )
                )
                assert slot.invalidated_at is not None
                assert slot.content_token != "old-token"
                assert slot.content == "retained body"
                assert slot.source_candidate_id == candidate["candidate_id"]
        finally:
            await engine.dispose()

    asyncio.run(exercise())
