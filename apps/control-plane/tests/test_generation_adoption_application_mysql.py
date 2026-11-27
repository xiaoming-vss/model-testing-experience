"""Real MySQL authorization, preparation and concurrent adoption boundaries."""

import asyncio
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from support import generation_candidate_graph as graph_fixture
from support.generation import generation_services
from support.memory_storage import Storage
from support.mysql_initialization import clean_schema as clean_schema
from support.mysql_initialization import mysql as mysql
from support.mysql_initialization import seed_row
from support.mysql_initialization import sessions as sessions

from testing_agent.core.errors import AppError
from testing_agent.domain.generation_root_fingerprints import fingerprint_root_input
from testing_agent.models import Base
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationReviewReceipt,
    AiGenerationStageContent,
)
from testing_agent.models.requirement import Requirement
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.schemas.generation_candidates import CandidateAdoptRequest, CurrentClearRequest
from testing_agent.services.generation_adoption_application import CandidateAdoptionApplication

DOCUMENT = b"verified document"
STAGE = dict(requirement_id="req", kind="requirement_analysis", stage="extracting_text")


@pytest.fixture
def material_graph(mysql, monkeypatch):
    """Seed requirement ``req`` with an available trial material ``m`` in an empty stage slot."""
    digest = sha256(DOCUMENT).hexdigest()
    root = fingerprint_root_input(
        "requirement_document",
        {
            "requirementId": "req",
            "documentFileId": "document",
            "documentHash": digest,
            "documentType": "docx",
            "documentFilename": "requirement.docx",
        },
    )
    monkeypatch.setattr(graph_fixture, "ROOT", root)
    monkeypatch.setattr(
        graph_fixture,
        "ROOT_JSON",
        {
            "snapshotId": root.snapshot_id,
            "resourceKind": root.resource_kind,
            "resourceId": root.resource_id,
            "contentHash": root.content_hash,
            "sourceBatchId": root.source_batch_id,
        },
    )
    material = graph_fixture.make_record("m", "requirement_analysis", "extracting_text")
    tables = Base.metadata.tables
    with mysql.begin() as conn:
        project = seed_row(conn, tables["projects"])
        actor = project["user_id"]
        sprint = seed_row(conn, tables["sprints"], {"project_id": project["project_id"]})
        seed_row(
            conn,
            tables["requirements"],
            {
                "requirement_id": "req",
                "sprint_id": sprint["sprint_id"],
                "document_type": "docx",
                "document_file_id": "document",
                "document_filename": "requirement.docx",
                "document_hash": digest,
            },
        )
        seed_row(
            conn,
            tables["stored_files"],
            {
                "file_id": "document",
                "project_id": project["project_id"],
                "uploaded_by": actor,
                "filename": "requirement.docx",
                "content_type": "application/octet-stream",
                "size": len(DOCUMENT),
                "sha256": digest,
                "bucket": "bucket",
                "object_key": "document",
                "staging_key": "",
                "status": "attached",
                "purpose": "requirement",
                "resource_type": "requirement",
                "resource_id": "req",
                "expires_at": datetime.now(UTC) + timedelta(days=1),
            },
        )
        task = seed_row(
            conn,
            tables["ai_generate_tasks"],
            {
                "project_id": project["project_id"],
                "sprint_id": sprint["sprint_id"],
                "requirement_id": "req",
                "task_type": "requirement_analysis",
            },
        )
        chain = seed_row(
            conn,
            tables["requirement_generation_chains"],
            {
                "requirement_id": "req",
                "kind": "requirement_analysis",
                "task_id": task["task_id"],
            },
        )
        stage = seed_row(
            conn,
            tables["ai_generation_stages"],
            {
                "task_id": task["task_id"],
                "stage": "extracting_text",
            },
        )
        seed_row(
            conn,
            tables["ai_generation_candidates"],
            {
                "candidate_id": "m",
                "snapshot_id": material.snapshot_id,
                "chain_id": chain["chain_id"],
                "stage_id": stage["id"],
                "candidate_token": "token-m",
                "current_attempt_id": "attempt-m",
                "disposition": "available",
                "generation_mode": "trial",
                "content": material.content,
                "format": material.format,
                "content_hash": material.content_hash,
                "basis_hash": material.basis_hash,
                "lineage_hash": material.lineage_hash,
                "source_manifest_json": material.source_manifest,
                "source_snapshot_json": graph_fixture.SOURCE_SNAPSHOT,
            },
        )
        seed_row(
            conn,
            tables["ai_generation_stage_contents"],
            {
                "chain_id": chain["chain_id"],
                "stage_id": stage["id"],
                "stage": "extracting_text",
                "source_candidate_id": None,
                "content_token": "empty-m",
            },
        )
    return SimpleNamespace(actor=actor, stage_id=stage["id"])


@pytest.fixture
def files():
    """File service over the seeded document; ``files.storage`` counts, blocks and refuses reads."""
    return SimpleNamespace(settings=SimpleNamespace(bucket="bucket"), storage=Storage(DOCUMENT))


def application(session, files):
    return CandidateAdoptionApplication(
        generation_services(AiGenerateTaskRepository(session), files=files).chain
    )


def adopt_request():
    return CandidateAdoptRequest(
        action="adopt",
        candidate_id="m",
        expected_candidate_token="token-m",
        expected_attempt_id="attempt-m",
        expected_current_token="empty-m",
        request_id=uuid4(),
    )


async def adopt(sessions, files, request, actor_id):
    async with sessions() as session:
        return await application(session, files).adopt(**STAGE, request=request, actor_id=actor_id)


async def clear(sessions, files, request, actor_id):
    async with sessions() as session:
        return await application(session, files).clear(**STAGE, request=request, actor_id=actor_id)


async def current_slot(sessions, stage_id):
    async with sessions() as session:
        return await session.scalar(
            sa.select(AiGenerationStageContent).where(AiGenerationStageContent.stage_id == stage_id)
        )


async def adopt_then_clear(sessions, files, actor_id):
    """Adopt ``m`` once and clear the slot once; returns the adoption request and clear result."""
    request = adopt_request()
    adopted = await adopt(sessions, files, request, actor_id)
    cleared = await clear(
        sessions,
        files,
        CurrentClearRequest(expected_current_token=adopted.content_token, request_id=uuid4()),
        actor_id,
    )
    return request, cleared


async def test_adoption_by_another_actor_is_refused_before_reading_the_document(
    material_graph, files, sessions
):
    with pytest.raises(AppError) as forbidden:
        await adopt(sessions, files, adopt_request(), "other")

    assert forbidden.value.http_code == 403
    assert files.storage.calls == 0


async def test_preview_reports_the_material_adoptable_without_side_effects(
    material_graph, files, sessions
):
    async with sessions() as session:
        previewed = await application(session, files).preview(
            **STAGE, request=adopt_request(), actor_id=material_graph.actor
        )
        frozen_at = (await session.get(AiGenerationCandidate, "m")).frozen_at
        receipts = await session.scalar(
            sa.select(sa.func.count()).select_from(AiGenerationReviewReceipt)
        )

    assert previewed.can_adopt
    assert frozen_at is None
    assert receipts == 0


async def test_document_replaced_during_the_read_rejects_the_adoption(
    material_graph, files, sessions
):
    files.storage.block = True
    pending = asyncio.create_task(adopt(sessions, files, adopt_request(), material_graph.actor))
    try:
        assert await asyncio.to_thread(files.storage.entered.wait, 5)
        async with sessions() as writer:
            await asyncio.wait_for(
                writer.execute(
                    sa.update(Requirement)
                    .where(Requirement.requirement_id == "req")
                    .values(document_filename="changed.docx")
                ),
                timeout=3,
            )
            await writer.commit()
        files.storage.release.set()

        with pytest.raises(AppError) as stale:
            await pending
        assert stale.value.data["reason"] in {"source_unknown", "source_stale"}
    finally:
        files.storage.release.set()
        await asyncio.gather(pending, return_exceptions=True)


async def test_concurrent_adoptions_of_one_request_adopt_once_and_replay(
    material_graph, files, sessions
):
    request, actor = adopt_request(), material_graph.actor

    results = await asyncio.gather(
        adopt(sessions, files, request, actor), adopt(sessions, files, request, actor)
    )

    async with sessions() as session:
        receipts = await session.scalar(
            sa.select(sa.func.count()).select_from(AiGenerationReviewReceipt)
        )
    slot = await current_slot(sessions, material_graph.stage_id)
    assert sorted(item.replayed for item in results) == [False, True]
    assert results[0].content_token == results[1].content_token
    assert receipts == 1
    assert slot.source_candidate_id == "m"


async def test_concurrent_clears_of_one_request_clear_once_and_replay(
    material_graph, files, sessions
):
    actor = material_graph.actor
    adopted = await adopt(sessions, files, adopt_request(), actor)
    request = CurrentClearRequest(expected_current_token=adopted.content_token, request_id=uuid4())

    results = await asyncio.gather(
        clear(sessions, files, request, actor), clear(sessions, files, request, actor)
    )

    assert sorted(item.replayed for item in results) == [False, True]
    assert results[0].content_token == results[1].content_token


async def test_replaying_the_adoption_after_a_clear_changes_nothing(
    material_graph, files, sessions
):
    actor = material_graph.actor
    request, cleared = await adopt_then_clear(sessions, files, actor)
    calls = files.storage.calls

    files.storage.fail = True
    replay = await adopt(sessions, files, request, actor)
    slot = await current_slot(sessions, material_graph.stage_id)

    assert replay.replayed and files.storage.calls == calls
    assert slot.source_candidate_id is None and slot.content_token == cleared.content_token
