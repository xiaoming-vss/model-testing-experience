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
from support.mysql_initialization import async_sessions, mysql, seed_row  # noqa: F401

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


def test_application_rechecks_authorization_and_replays_on_mysql(mysql, monkeypatch):  # noqa: F811
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

    async def exercise():
        engine, factory = async_sessions(mysql)
        storage = Storage(DOCUMENT)
        files = SimpleNamespace(settings=SimpleNamespace(bucket="bucket"), storage=storage)

        def application(session):
            return CurrentImportApplication(
                generation_services(AiGenerateTaskRepository(session), files=files).chain,
                secret=SECRET,
            )

        try:
            async with factory() as session:
                app = application(session)
                with pytest.raises(AppError) as forbidden:
                    await app.preview(
                        requirement_id="req",
                        kind="function",
                        stage="detailed_cases",
                        current_token="current-d",
                        target_id="",
                        actor_id="other",
                        now=100,
                    )
                assert forbidden.value.http_code == 403 and storage.calls == 0
                preview = await app.preview(
                    requirement_id="req",
                    kind="function",
                    stage="detailed_cases",
                    current_token="current-d",
                    target_id="",
                    actor_id=actor,
                    now=100,
                )
                assert preview.requires_confirmation
            request = CurrentImportRequest(
                expected_current_token=preview.current_token,
                expected_lineage_hash=preview.full_lineage_hash,
                preview_token=preview.preview_token,
                request_id=uuid4(),
                confirm_overwrite=True,
            )

            async def submit():
                async with factory() as session:
                    return await application(session).execute(
                        requirement_id="req",
                        kind="function",
                        stage="detailed_cases",
                        request=request,
                        actor_id=actor,
                        now=101,
                    )

            results = await asyncio.gather(submit(), submit())
            assert sorted(result["replayed"] for result in results) == [False, True]
            assert results[0]["importRecords"] == results[1]["importRecords"]
            async with factory() as session:
                assert (
                    await session.scalar(sa.select(sa.func.count()).select_from(AiGenerateImport))
                    == 1
                )
                assert (
                    await session.scalar(
                        sa.select(sa.func.count()).select_from(AiGenerateImportRequest)
                    )
                    == 1
                )
                updated = await session.scalar(
                    sa.select(FunctionTestCase).where(FunctionTestCase.case_id == "case")
                )
                assert updated is not None and updated.steps == "login"
                await delete_chain_storage_for_task(session, task_id=tasks["function"]["task_id"])
                await session.commit()
            storage.fail = True
            async with factory() as session:
                replay = await application(session).execute(
                    requirement_id="req",
                    kind="function",
                    stage="detailed_cases",
                    request=request,
                    actor_id=actor,
                    now=1000,
                )
                assert replay["replayed"] and replay["importRecords"] == results[0]["importRecords"]
        finally:
            await engine.dispose()

    asyncio.run(exercise())
