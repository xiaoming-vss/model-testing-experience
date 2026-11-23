"""Real MySQL completion races append at most one candidate."""

import asyncio
from copy import deepcopy
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.generation_candidate_graph import SOURCE_SNAPSHOT, fixture_graph
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.core.errors import AppError
from testing_agent.domain.generation_root_fingerprints import fingerprint_root_input
from testing_agent.models import Base
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.generation_candidates import AiGenerationCandidate
from testing_agent.schemas.generation_candidates import CandidateRunRequest
from testing_agent.services.generation_candidate_dispatch import dispatch_candidate_stage
from testing_agent.services.stage_storage import DirectStageStorage
from testing_agent.services.stage_storage.worker import StageWorkerTransitions


def test_concurrent_completion_does_not_duplicate_candidate(mysql):  # noqa: F811
    tables = Base.metadata.tables
    material = fixture_graph()["m"]
    with mysql.begin() as connection:
        project = seed_row(connection, tables["projects"])
        sprint = seed_row(connection, tables["sprints"], {"project_id": project["project_id"]})
        requirement = seed_row(
            connection,
            tables["requirements"],
            {
                "requirement_id": "req",
                "sprint_id": sprint["sprint_id"],
            },
        )
        task = seed_row(
            connection,
            tables["ai_generate_tasks"],
            {
                "task_type": "requirement_analysis",
                "project_id": project["project_id"],
                "sprint_id": sprint["sprint_id"],
                "requirement_id": requirement["requirement_id"],
            },
        )
        chain = seed_row(
            connection,
            tables["requirement_generation_chains"],
            {
                "task_id": task["task_id"],
                "kind": "requirement_analysis",
                "requirement_id": "req",
            },
        )
        stage = seed_row(
            connection,
            tables["ai_generation_stages"],
            {
                "task_id": task["task_id"],
                "stage": "extracting_text",
            },
        )
    snapshot = {
        **deepcopy(SOURCE_SNAPSHOT),
        "candidateProtocol": "single-current/1",
        "candidateInput": deepcopy(material.source_manifest),
        "candidateBasisHash": material.basis_hash,
    }

    async def run():
        engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                attempt = await DirectStageStorage(session).prepare(
                    stage["id"],
                    worker_task_id="worker",
                    requested_by="u",
                    input_snapshot=snapshot,
                    allow_multiple_candidates=True,
                )
                attempt_id = attempt.id
                await session.commit()

            async def complete():
                async with factory() as session:
                    try:
                        await StageWorkerTransitions(session).completed(
                            stage["id"],
                            attempt_id,
                            "worker",
                            content="output",
                            output_format="text",
                            output_context=None,
                        )
                        await session.commit()
                        return "success"
                    except AppError:
                        await session.rollback()
                        return "rejected"

            assert sorted(await asyncio.gather(complete(), complete())) == ["rejected", "success"]
            async with factory() as session:
                rows = (
                    await session.scalars(
                        sa.select(AiGenerationCandidate).where(
                            AiGenerationCandidate.origin_attempt_id == attempt_id
                        )
                    )
                ).all()
                assert len(rows) == 1 and rows[0].content == "output"
                assert rows[0].chain_id == chain["chain_id"]

            source = {
                "requirementId": "req",
                "documentFileId": "file",
                "documentHash": "hash",
                "documentType": "docx",
                "documentFilename": "requirement.docx",
                "sourceContent": "/internal/ai-worker/tasks/id/requirement-document",
                "documentDownloadUrl": "/internal/ai-worker/tasks/id/requirement-document",
            }
            root = fingerprint_root_input("requirement_document", source)

            async def dispatch():
                async with factory() as session:
                    try:
                        task_row = await session.scalar(
                            sa.select(AiGenerateTask).where(
                                AiGenerateTask.task_id == task["task_id"]
                            )
                        )
                        assert task_row is not None
                        await dispatch_candidate_stage(
                            session,
                            task=task_row,
                            kind="requirement_analysis",
                            stage="extracting_text",
                            request=CandidateRunRequest(connection_id="llm", request_id=uuid4()),
                            actor_id="u",
                            source=source,
                            direct_roots=(root,),
                            current_root_hashes={root.key: root.content_hash},
                        )
                        await session.commit()
                        return "success"
                    except AppError:
                        await session.rollback()
                        return "rejected"

            assert sorted(await asyncio.gather(dispatch(), dispatch())) == ["rejected", "success"]
        finally:
            await engine.dispose()

    asyncio.run(run())
