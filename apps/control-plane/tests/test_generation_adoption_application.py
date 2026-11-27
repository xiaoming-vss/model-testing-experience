"""Adoption checks authorization, real roots and the frozen candidate sources."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import pytest
from support import generation_candidate_graph as graph_fixture
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401
from support.generation import generation_services
from support.generation_source_seed import seed_graph
from support.memory_storage import Storage

from testing_agent.core.errors import AppError
from testing_agent.domain.generation_root_fingerprints import fingerprint_root_input
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationReviewReceipt,
    AiGenerationStageContent,
)
from testing_agent.models.requirement import Requirement
from testing_agent.models.stored_file import StoredFile
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.schemas.generation_candidates import CandidateAdoptRequest, CurrentClearRequest
from testing_agent.services.generation_adoption_application import CandidateAdoptionApplication


def prepare(sync, monkeypatch):
    data = b"verified document"
    digest = sha256(data).hexdigest()
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
    graph = seed_graph(sync)
    requirement = sync.query(Requirement).filter_by(requirement_id="req").one()
    requirement.document_type, requirement.document_file_id = "docx", "document"
    requirement.document_filename, requirement.document_hash = "requirement.docx", digest
    sync.add(
        StoredFile(
            file_id="document",
            project_id="p",
            uploaded_by="u",
            filename="requirement.docx",
            content_type="application/octet-stream",
            size=len(data),
            sha256=digest,
            bucket="bucket",
            object_key="document",
            staging_key="",
            status="attached",
            purpose="requirement",
            resource_type="requirement",
            resource_id="req",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    for key, record in graph.items():
        candidate = sync.query(AiGenerationCandidate).filter_by(candidate_id=key).one()
        candidate.current_attempt_id = f"attempt-{key}"
        sync.add(
            AiGenerationStageContent(
                stage_id=candidate.stage_id,
                chain_id=candidate.chain_id,
                stage=record.stage,
                content_token=f"empty-{key}",
            )
        )
    sync.commit()
    storage = Storage(data)
    files = SimpleNamespace(settings=SimpleNamespace(bucket="bucket"), storage=storage)
    session = AsyncSessionAdapter(sync)
    app = CandidateAdoptionApplication(
        generation_services(AiGenerateTaskRepository(session), files=files).chain
    )
    return session, storage, app


def body(key):
    return CandidateAdoptRequest(
        action="adopt",
        candidate_id=key,
        expected_candidate_token=f"token-{key}",
        expected_attempt_id=f"attempt-{key}",
        expected_current_token=f"empty-{key}",
        request_id=uuid4(),
    )


async def test_adoption_is_independent_of_upstream_and_replays_without_reading_file(
    database,  # noqa: F811
    monkeypatch,
):
    sync, _, _ = database
    _, storage, app = prepare(sync, monkeypatch)

    async def adopt(key, kind, stage, request):
        return await app.adopt(
            requirement_id="req", kind=kind, stage=stage, request=request, actor_id="u"
        )

    points = body("p")
    preview_options = dict(
        requirement_id="req", kind="function", stage="case_names", request=points, actor_id="u"
    )
    preview = await app.preview(**preview_options)
    assert preview.can_adopt and not preview.blocking_sources
    adopted = await adopt("p", "function", "case_names", points)
    assert not adopted.replayed
    slot = sync.query(AiGenerationStageContent).filter_by(stage_id="stage-p").one()
    assert slot.source_candidate_id == "p" and slot.content_token == adopted.content_token
    assert all(candidate.frozen_at is not None for candidate in sync.query(AiGenerationCandidate))
    clear_body = CurrentClearRequest(
        expected_current_token=adopted.content_token, request_id=uuid4()
    )
    clear_options = dict(
        requirement_id="req", kind="function", stage="case_names", request=clear_body
    )
    with pytest.raises(AppError) as forbidden:
        await app.clear(**clear_options, actor_id="other")
    assert forbidden.value.http_code == 403
    cleared = await app.clear(**clear_options, actor_id="u")
    calls = storage.calls
    storage.fail = True
    replay = await adopt("p", "function", "case_names", points)
    assert (
        replay.replayed and replay.content_token == adopted.content_token and storage.calls == calls
    )
    slot = sync.query(AiGenerationStageContent).filter_by(stage_id="stage-p").one()
    assert slot.source_candidate_id is None and slot.content_token == cleared.content_token
    with pytest.raises(AppError):
        await adopt(
            "p", "function", "case_names", points.model_copy(update={"comment": "different"})
        )
    storage.fail = False
    new_request = points.model_copy(
        update={"request_id": uuid4(), "expected_current_token": cleared.content_token}
    )
    newly_adopted = await adopt("p", "function", "case_names", new_request)
    replayed_clear = await app.clear(**clear_options, actor_id="u")
    assert replayed_clear.replayed and replayed_clear.content_token == cleared.content_token
    slot = sync.query(AiGenerationStageContent).filter_by(stage_id="stage-p").one()
    assert slot.source_candidate_id == "p" and slot.content_token == newly_adopted.content_token


async def test_unauthorized_or_replaced_document_cannot_be_adopted(database, monkeypatch):  # noqa: F811
    sync, _, _ = database
    _, storage, app = prepare(sync, monkeypatch)
    options = dict(
        requirement_id="req",
        kind="requirement_analysis",
        stage="extracting_text",
        request=body("m"),
    )
    with pytest.raises(AppError) as forbidden:
        await app.adopt(**options, actor_id="other")
    assert forbidden.value.http_code == 403 and storage.calls == 0
    storage.data = b"modified"
    with pytest.raises(AppError) as stale:
        await app.adopt(**options, actor_id="u")
    assert stale.value.data["reason"] == "source_unknown"
    assert sync.query(AiGenerationReviewReceipt).count() == 0
    assert (
        sync.query(AiGenerationStageContent).filter_by(stage_id="stage-m").one().source_candidate_id
        is None
    )
