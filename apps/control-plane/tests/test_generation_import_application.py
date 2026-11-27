"""The application boundary authorizes, prepares real roots, and safely replays."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import pytest
from support import generation_candidate_graph as source_graph
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401
from support.generation import generation_services
from support.generation_import_seed import seed_import_graph
from support.memory_storage import Storage

from testing_agent.core.errors import AppError
from testing_agent.domain.generation_content_hash import generation_content_hash
from testing_agent.domain.generation_root_fingerprints import fingerprint_root_input
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
)
from testing_agent.models.requirement import Requirement
from testing_agent.models.stored_file import StoredFile
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.generation_current_chain import delete_chain_storage_for_task
from testing_agent.schemas.generation_candidates import CurrentImportRequest
from testing_agent.services.generation_import_application import CurrentImportApplication

SECRET = "test-only-preview-signing-key-32-bytes"
OUTPUT = """cases:
  - module: module
    title: existing
    steps: login
    expected_results: success
"""


def setup(sync, monkeypatch):
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
    monkeypatch.setattr(source_graph, "ROOT", root)
    monkeypatch.setattr(
        source_graph,
        "ROOT_JSON",
        {
            "snapshotId": root.snapshot_id,
            "resourceKind": root.resource_kind,
            "resourceId": root.resource_id,
            "contentHash": root.content_hash,
            "sourceBatchId": root.source_batch_id,
        },
    )
    seed_import_graph(sync)
    req = sync.query(Requirement).filter_by(requirement_id="req").one()
    req.document_type, req.document_file_id = "docx", "document"
    req.document_filename, req.document_hash = "requirement.docx", digest
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
    candidate = sync.query(AiGenerationCandidate).filter_by(candidate_id="d").one()
    slot = sync.query(AiGenerationStageContent).filter_by(stage_id="stage-d").one()
    for item in (candidate, slot):
        item.content, item.format = OUTPUT, "yaml"
        item.content_hash = generation_content_hash(OUTPUT, "yaml")
    sync.add(FunctionTestSuite(suite_id="suite", requirement_id="req", name="module"))
    sync.flush()
    sync.add(FunctionTestCase(case_id="case", suite_id="suite", title="existing", module="module"))
    sync.commit()
    storage = Storage(data)
    files = SimpleNamespace(settings=SimpleNamespace(bucket="bucket"), storage=storage)
    session = AsyncSessionAdapter(sync)
    bundle = generation_services(AiGenerateTaskRepository(session), files=files)
    return session, storage, CurrentImportApplication(bundle.chain, secret=SECRET)


async def test_authorized_import_prepares_roots_and_replays_without_source(database, monkeypatch):  # noqa: F811
    sync, _, _ = database
    session, storage, app = setup(sync, monkeypatch)
    preview = await app.preview(
        requirement_id="req",
        kind="function",
        stage="detailed_cases",
        current_token="current-d",
        target_id="",
        actor_id="u",
        now=100,
    )
    assert preview.requires_confirmation and storage.calls == 1
    assert sync.query(FunctionTestCase).filter_by(case_id="case").one().steps == ""
    request = CurrentImportRequest(
        expected_current_token=preview.current_token,
        expected_lineage_hash=preview.full_lineage_hash,
        preview_token=preview.preview_token,
        request_id=uuid4(),
        confirm_overwrite=True,
    )
    result = await app.execute(
        requirement_id="req",
        kind="function",
        stage="detailed_cases",
        request=request,
        actor_id="u",
        now=101,
    )
    assert result["imported"] and not result["replayed"] and storage.calls == 2
    assert sync.query(FunctionTestCase).filter_by(case_id="case").one().steps == "login"
    await delete_chain_storage_for_task(session, task_id="task")
    sync.commit()
    storage.fail = True
    replay = await app.execute(
        requirement_id="req",
        kind="function",
        stage="detailed_cases",
        request=request,
        actor_id="u",
        now=1000,
    )
    assert replay["replayed"] and replay["importRecords"] == result["importRecords"]
    with pytest.raises(AppError) as rejected:
        await app.execute(
            requirement_id="req",
            kind="function",
            stage="detailed_cases",
            request=request,
            actor_id="other",
            now=1000,
        )
    assert rejected.value.http_code == 403
    assert storage.calls == 2


async def test_file_replaced_after_preview_blocks_import(database, monkeypatch):  # noqa: F811
    sync, _, _ = database
    _, storage, app = setup(sync, monkeypatch)
    preview = await app.preview(
        requirement_id="req",
        kind="function",
        stage="detailed_cases",
        current_token="current-d",
        target_id="",
        actor_id="u",
        now=100,
    )
    storage.data = b"modified object"
    body = CurrentImportRequest(
        expected_current_token=preview.current_token,
        expected_lineage_hash=preview.full_lineage_hash,
        preview_token=preview.preview_token,
        request_id=uuid4(),
        confirm_overwrite=True,
    )
    with pytest.raises(AppError) as rejected:
        await app.execute(
            requirement_id="req",
            kind="function",
            stage="detailed_cases",
            request=body,
            actor_id="u",
            now=101,
        )
    assert rejected.value.http_code == 400
    assert sync.query(FunctionTestCase).filter_by(case_id="case").one().steps == ""
