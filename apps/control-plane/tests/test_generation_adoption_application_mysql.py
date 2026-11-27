"""Real MySQL authorization, preparation and concurrent adoption boundaries."""

import asyncio
import threading
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from support import generation_candidate_graph as graph_fixture
from support.generation import generation_services
from support.mysql_initialization import async_sessions, mysql, seed_row  # noqa: F401

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


class Body:
    def iter_chunks(self, chunk_size):
        yield DOCUMENT

    def close(self):
        pass


class Storage:
    def __init__(self):
        self.calls = 0
        self.block = False
        self.fail = False
        self.entered = threading.Event()
        self.release = threading.Event()

    def get_object(self, key):
        self.calls += 1
        assert not self.fail and key == "document"
        if self.block:
            self.entered.set()
            if not self.release.wait(10):
                raise RuntimeError("test storage timed out")
        return {"Body": Body()}


def test_adoption_application_rechecks_document_and_serializes_retries(mysql, monkeypatch):  # noqa: F811
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

    async def exercise():
        engine, factory = async_sessions(mysql)
        storage = Storage()
        files = SimpleNamespace(settings=SimpleNamespace(bucket="bucket"), storage=storage)
        request = CandidateAdoptRequest(
            action="adopt",
            candidate_id="m",
            expected_candidate_token="token-m",
            expected_attempt_id="attempt-m",
            expected_current_token="empty-m",
            request_id=uuid4(),
        )

        def application(session):
            return CandidateAdoptionApplication(
                generation_services(AiGenerateTaskRepository(session), files=files).chain
            )

        async def submit():
            async with factory() as session:
                return await application(session).adopt(
                    requirement_id="req",
                    kind="requirement_analysis",
                    stage="extracting_text",
                    request=request,
                    actor_id=actor,
                )

        try:
            async with factory() as session:
                with pytest.raises(AppError) as forbidden:
                    await application(session).adopt(
                        requirement_id="req",
                        kind="requirement_analysis",
                        stage="extracting_text",
                        request=request,
                        actor_id="other",
                    )
                assert forbidden.value.http_code == 403 and storage.calls == 0
                preview = await application(session).preview(
                    requirement_id="req",
                    kind="requirement_analysis",
                    stage="extracting_text",
                    request=request,
                    actor_id=actor,
                )
                assert preview.can_adopt
                assert (await session.get(AiGenerationCandidate, "m")).frozen_at is None
                assert (
                    await session.scalar(
                        sa.select(sa.func.count()).select_from(AiGenerationReviewReceipt)
                    )
                    == 0
                )
            storage.block = True
            pending = asyncio.create_task(submit())
            assert await asyncio.to_thread(storage.entered.wait, 5)
            async with factory() as writer:
                await asyncio.wait_for(
                    writer.execute(
                        sa.update(Requirement)
                        .where(Requirement.requirement_id == "req")
                        .values(document_filename="changed.docx")
                    ),
                    timeout=3,
                )
                await writer.commit()
            storage.release.set()
            with pytest.raises(AppError) as stale:
                await pending
            assert stale.value.data["reason"] in {"source_unknown", "source_stale"}
            async with factory() as writer:
                await writer.execute(
                    sa.update(Requirement)
                    .where(Requirement.requirement_id == "req")
                    .values(document_filename="requirement.docx")
                )
                await writer.commit()
            storage.block = False
            results = await asyncio.gather(submit(), submit())
            assert sorted(item.replayed for item in results) == [False, True]
            assert results[0].content_token == results[1].content_token
            async with factory() as session:
                assert (
                    await session.scalar(
                        sa.select(sa.func.count()).select_from(AiGenerationReviewReceipt)
                    )
                    == 1
                )
                slot = await session.scalar(
                    sa.select(AiGenerationStageContent).where(
                        AiGenerationStageContent.stage_id == stage["id"]
                    )
                )
                assert slot.source_candidate_id == "m"
            clear_body = CurrentClearRequest(
                expected_current_token=results[0].content_token, request_id=uuid4()
            )

            async def clear():
                async with factory() as session:
                    return await application(session).clear(
                        requirement_id="req",
                        kind="requirement_analysis",
                        stage="extracting_text",
                        request=clear_body,
                        actor_id=actor,
                    )

            clear_results = await asyncio.gather(clear(), clear())
            assert sorted(item.replayed for item in clear_results) == [False, True]
            assert clear_results[0].content_token == clear_results[1].content_token
            async with factory() as session:
                calls = storage.calls
                storage.fail = True
                replay = await application(session).adopt(
                    requirement_id="req",
                    kind="requirement_analysis",
                    stage="extracting_text",
                    request=request,
                    actor_id=actor,
                )
                assert replay.replayed and storage.calls == calls
                session.expire_all()
                slot = await session.scalar(
                    sa.select(AiGenerationStageContent).where(
                        AiGenerationStageContent.stage_id == stage["id"]
                    )
                )
                assert (
                    slot.source_candidate_id is None
                    and slot.content_token == clear_results[0].content_token
                )
        finally:
            storage.release.set()
            await engine.dispose()

    asyncio.run(exercise())
