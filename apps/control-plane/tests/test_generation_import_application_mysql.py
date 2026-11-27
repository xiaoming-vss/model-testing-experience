"""Verify the authorized current import boundary against real MySQL transactions."""

import asyncio
from dataclasses import replace
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
from testing_agent.domain.generation_content_hash import generation_content_hash
from testing_agent.domain.generation_root_fingerprints import fingerprint_root_input
from testing_agent.models import Base
from testing_agent.models.ai_generate_import import AiGenerateImport, AiGenerateImportRequest
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.generation_current_chain import delete_chain_storage_for_task
from testing_agent.schemas.generation_candidates import CurrentImportRequest
from testing_agent.services.generation_import_application import CurrentImportApplication

SECRET = "test-only-preview-signing-key-32-bytes"
DOCUMENT = b"verified requirement document"
OUTPUT = (
    "cases:\n  - module: module\n    title: existing\n"
    "    steps: login\n    expected_results: success\n"
)
TARGET = dict(requirement_id="req", kind="function", stage="detailed_cases")


@pytest.fixture
def import_graph(mysql, monkeypatch):
    """Seed requirement ``req`` whose candidate graph ends in the importable ``d``."""
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
    graph = graph_fixture.fixture_graph()
    final = graph_fixture.make_record(
        "d",
        "function",
        "detailed_cases",
        parents=(graph["a"], graph["p"]),
        ancestors=(graph["m"], graph["a"], graph["p"]),
    )
    graph["d"] = replace(
        final, content=OUTPUT, format="yaml", content_hash=generation_content_hash(OUTPUT, "yaml")
    )
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
        scope = {
            "project_id": project["project_id"],
            "sprint_id": sprint["sprint_id"],
            "requirement_id": "req",
        }
        tasks = {
            kind: seed_row(conn, tables["ai_generate_tasks"], {**scope, "task_type": task_type})
            for kind, task_type in (
                ("requirement_analysis", "requirement_analysis"),
                ("function", "functional_case_generate"),
            )
        }
        chains = {
            kind: seed_row(
                conn,
                tables["requirement_generation_chains"],
                {
                    "requirement_id": "req",
                    "kind": kind,
                    "task_id": task["task_id"],
                },
            )
            for kind, task in tasks.items()
        }
        for key, item in graph.items():
            stage = seed_row(
                conn,
                tables["ai_generation_stages"],
                {"task_id": tasks[item.chain_kind]["task_id"], "stage": item.stage},
            )
            common = {
                "chain_id": chains[item.chain_kind]["chain_id"],
                "stage_id": stage["id"],
                "content": item.content,
                "format": item.format,
                "content_hash": item.content_hash,
                "basis_hash": item.basis_hash,
                "lineage_hash": item.lineage_hash,
                "source_manifest_json": item.source_manifest,
                "source_snapshot_json": graph_fixture.SOURCE_SNAPSHOT,
            }
            seed_row(
                conn,
                tables["ai_generation_candidates"],
                {
                    **common,
                    "candidate_id": key,
                    "snapshot_id": item.snapshot_id,
                    "candidate_token": f"token-{key}",
                    "disposition": "available",
                    "generation_mode": "trial",
                },
            )
            seed_row(
                conn,
                tables["ai_generation_stage_contents"],
                {
                    **common,
                    "stage": item.stage,
                    "source_candidate_id": key,
                    "content_token": f"current-{key}",
                },
            )
        seed_row(
            conn,
            tables["function_test_suites"],
            {"suite_id": "suite", "requirement_id": "req", "name": "module"},
        )
        seed_row(
            conn,
            tables["function_test_cases"],
            {"case_id": "case", "suite_id": "suite", "title": "existing", "module": "module"},
        )
    return SimpleNamespace(actor=actor, function_task_id=tasks["function"]["task_id"])


@pytest.fixture
def files():
    """File service over the seeded document; ``files.storage`` counts and can refuse reads."""
    return SimpleNamespace(settings=SimpleNamespace(bucket="bucket"), storage=Storage(DOCUMENT))


def application(session, files):
    return CurrentImportApplication(
        generation_services(AiGenerateTaskRepository(session), files=files).chain, secret=SECRET
    )


async def preview(sessions, files, actor_id):
    """Preview the current ``d`` for ``actor_id``."""
    async with sessions() as session:
        return await application(session, files).preview(
            **TARGET, current_token="current-d", target_id="", actor_id=actor_id, now=100
        )


def confirmed_request(previewed):
    return CurrentImportRequest(
        expected_current_token=previewed.current_token,
        expected_lineage_hash=previewed.full_lineage_hash,
        preview_token=previewed.preview_token,
        request_id=uuid4(),
        confirm_overwrite=True,
    )


async def execute(sessions, files, request, actor_id, now=101):
    async with sessions() as session:
        return await application(session, files).execute(
            **TARGET, request=request, actor_id=actor_id, now=now
        )


async def test_preview_by_another_actor_is_refused_before_reading_the_document(
    import_graph, files, sessions
):
    with pytest.raises(AppError) as forbidden:
        await preview(sessions, files, "other")

    assert forbidden.value.http_code == 403
    assert files.storage.calls == 0


async def test_authorized_preview_requires_confirmation(import_graph, files, sessions):
    previewed = await preview(sessions, files, import_graph.actor)

    assert previewed.requires_confirmation


async def test_concurrent_executes_of_one_request_import_once_and_replay(
    import_graph, files, sessions
):
    actor = import_graph.actor
    request = confirmed_request(await preview(sessions, files, actor))

    results = await asyncio.gather(
        execute(sessions, files, request, actor), execute(sessions, files, request, actor)
    )

    async with sessions() as session:
        imports = await session.scalar(sa.select(sa.func.count()).select_from(AiGenerateImport))
        requests = await session.scalar(
            sa.select(sa.func.count()).select_from(AiGenerateImportRequest)
        )
        updated = await session.scalar(
            sa.select(FunctionTestCase).where(FunctionTestCase.case_id == "case")
        )
    assert sorted(result["replayed"] for result in results) == [False, True]
    assert results[0]["importRecords"] == results[1]["importRecords"]
    assert imports == 1
    assert requests == 1
    assert updated is not None and updated.steps == "login"


async def test_replay_after_chain_storage_removal_returns_the_receipt_without_a_read(
    import_graph, files, sessions
):
    actor = import_graph.actor
    request = confirmed_request(await preview(sessions, files, actor))
    imported = await execute(sessions, files, request, actor)
    async with sessions() as session:
        await delete_chain_storage_for_task(session, task_id=import_graph.function_task_id)
        await session.commit()

    files.storage.fail = True
    replay = await execute(sessions, files, request, actor, now=1000)

    assert replay["replayed"] and replay["importRecords"] == imported["importRecords"]
