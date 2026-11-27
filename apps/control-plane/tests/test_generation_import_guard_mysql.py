"""Real MySQL locks and preview bindings protect formal import sources and targets."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from support.generation import generation_services
from support.generation_candidate_graph import ROOT, SOURCE_SNAPSHOT, fixture_graph, make_record
from support.mysql_initialization import clean_schema as clean_schema
from support.mysql_initialization import mysql as mysql
from support.mysql_initialization import seed_row
from support.mysql_initialization import sessions as sessions

from testing_agent.domain.generation_content_hash import generation_content_hash
from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models import Base
from testing_agent.models.ai_generate_import import AiGenerateImport, AiGenerateImportRequest
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.api_assert_rule import ApiAssertRule
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.generation_candidates import AiGenerationStageContent
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.generation_current_chain import delete_chain_storage_for_task
from testing_agent.repositories.generation_import_targets import lock_import_target_state
from testing_agent.schemas.generation_candidates import CurrentImportRequest
from testing_agent.services import generation_current_import as import_module
from testing_agent.services.generation_current_import import CurrentImportCoordinator
from testing_agent.services.generation_import_guard import (
    prepare_import_preview,
    verify_import_preview,
)

SECRET = "test-only-preview-signing-key-32-bytes"
OUTPUT = """cases:
  - module: module
    title: existing
    steps: login
    expected_results: success
  - module: second-module
    title: second
    steps: register
    expected_results: created
"""
# The coordinator previews and executes as a given actor; the guard helpers act as "u".
COORDINATOR = dict(
    requirement_id="req",
    kind="function",
    stage="detailed_cases",
    current_root_hashes={ROOT.key: ROOT.content_hash},
    secret=SECRET,
)
GUARD = dict(**COORDINATOR, actor_id="u")


@pytest.fixture
def import_targets(mysql):
    """Requirement ``req`` with the graph ending in ``d``, one function case and one API case."""
    tables = Base.metadata.tables
    graph = fixture_graph()
    graph["d"] = make_record(
        "d",
        "function",
        "detailed_cases",
        parents=(graph["a"], graph["p"]),
        ancestors=(graph["m"], graph["a"], graph["p"]),
    )
    graph["d"] = replace(
        graph["d"],
        content=OUTPUT,
        format="yaml",
        content_hash=generation_content_hash(OUTPUT, "yaml"),
    )
    with mysql.begin() as connection:
        project = seed_row(connection, tables["projects"])
        sprint = seed_row(connection, tables["sprints"], {"project_id": project["project_id"]})
        seed_row(
            connection,
            tables["requirements"],
            {"requirement_id": "req", "sprint_id": sprint["sprint_id"]},
        )
        scope = {
            "project_id": project["project_id"],
            "sprint_id": sprint["sprint_id"],
            "requirement_id": "req",
        }
        tasks = {
            "requirement_analysis": seed_row(
                connection,
                tables["ai_generate_tasks"],
                {**scope, "task_type": "requirement_analysis"},
            ),
            "function": seed_row(
                connection,
                tables["ai_generate_tasks"],
                {**scope, "task_type": "functional_case_generate"},
            ),
        }
        chains = {
            kind: seed_row(
                connection,
                tables["requirement_generation_chains"],
                {"requirement_id": "req", "kind": kind, "task_id": task["task_id"]},
            )
            for kind, task in tasks.items()
        }
        stage_ids = {}
        for key, record in graph.items():
            stage = seed_row(
                connection,
                tables["ai_generation_stages"],
                {
                    "task_id": tasks[record.chain_kind]["task_id"],
                    "stage": record.stage,
                },
            )
            stage_ids[key] = stage["id"]
            candidate = seed_row(
                connection,
                tables["ai_generation_candidates"],
                {
                    "candidate_id": key,
                    "snapshot_id": record.snapshot_id,
                    "chain_id": chains[record.chain_kind]["chain_id"],
                    "stage_id": stage["id"],
                    "candidate_token": f"token-{key}",
                    "disposition": "available",
                    "generation_mode": "trial",
                    "content": record.content,
                    "format": record.format,
                    "content_hash": record.content_hash,
                    "basis_hash": record.basis_hash,
                    "lineage_hash": record.lineage_hash,
                    "source_manifest_json": record.source_manifest,
                    "source_snapshot_json": SOURCE_SNAPSHOT,
                },
            )
            seed_row(
                connection,
                tables["ai_generation_stage_contents"],
                {
                    "chain_id": chains[record.chain_kind]["chain_id"],
                    "stage_id": stage["id"],
                    "stage": record.stage,
                    "content": record.content,
                    "format": record.format,
                    "content_hash": record.content_hash,
                    "basis_hash": record.basis_hash,
                    "lineage_hash": record.lineage_hash,
                    "source_manifest_json": record.source_manifest,
                    "source_snapshot_json": SOURCE_SNAPSHOT,
                    "source_candidate_id": candidate["candidate_id"],
                    "content_token": f"current-{key}",
                },
            )
        suite = seed_row(
            connection,
            tables["function_test_suites"],
            {
                "suite_id": "suite",
                "requirement_id": "req",
                "name": "module",
            },
        )
        seed_row(
            connection,
            tables["function_test_cases"],
            {
                "case_id": "case",
                "suite_id": suite["suite_id"],
                "title": "existing",
                "module": "module",
            },
        )
        seed_row(
            connection,
            tables["api_collections"],
            {"collection_id": "api-target", "requirement_id": "req", "name": "api"},
        )
        seed_row(
            connection,
            tables["api_cases"],
            {
                "case_id": "api-case",
                "collection_id": "api-target",
                "name": "api case",
                "method": "GET",
                "url_template": "/api",
            },
        )
    return SimpleNamespace(
        owner=project["user_id"],
        material_stage=stage_ids["m"],
        function_task_id=tasks["function"]["task_id"],
    )


async def prepare(session):
    """Guard preview of the current ``d``; it locks the formal targets until commit."""
    return await prepare_import_preview(
        session, current_token="current-d", target_id="", now=100, **GUARD
    )


def bound_request(preview):
    """Import request bound to the lineage and preview token of ``preview``."""
    return CurrentImportRequest(
        expected_current_token="current-d",
        expected_lineage_hash=preview.source.full_lineage_hash,
        preview_token=preview.preview_token,
        request_id=uuid4(),
    )


async def confirmed_request(sessions, owner):
    """Coordinator preview as ``owner``; returns the request that confirms that preview."""
    async with sessions() as session:
        bundle = generation_services(AiGenerateTaskRepository(session))
        preview = await CurrentImportCoordinator(bundle.imports, bundle.api_importer).preview(
            **COORDINATOR, current_token="current-d", target_id="", actor_id=owner, now=100
        )
        assert preview.requires_confirmation
        await session.commit()
    return CurrentImportRequest(
        expected_current_token=preview.current_token,
        expected_lineage_hash=preview.full_lineage_hash,
        preview_token=preview.preview_token,
        request_id=uuid4(),
        confirm_overwrite=True,
    )


async def execute(sessions, request, owner):
    """Coordinator execute as ``owner``; returns the result."""
    async with sessions() as session:
        bundle = generation_services(AiGenerateTaskRepository(session))
        result = await CurrentImportCoordinator(bundle.imports, bundle.api_importer).execute(
            **COORDINATOR, request=request, actor_id=owner, now=101
        )
        await session.commit()
        return result


async def test_preview_holds_the_formal_targets_until_it_ends(sessions, import_targets):
    async with sessions() as reader, sessions() as writer:
        await prepare(reader)
        started = asyncio.Event()

        async def edit_case():
            started.set()
            await writer.execute(
                sa.update(FunctionTestCase)
                .where(FunctionTestCase.case_id == "case")
                .values(title="changed")
            )
            await writer.commit()

        editing = asyncio.create_task(edit_case())
        await started.wait()
        blocked = not (await asyncio.wait({editing}, timeout=0.2))[0]
        await reader.commit()
        await asyncio.wait_for(editing, timeout=10)

    assert blocked


async def test_verification_rejects_a_target_changed_after_the_preview(sessions, import_targets):
    async with sessions() as reader, sessions() as writer:
        request = bound_request(await prepare(reader))
        await reader.commit()
        await writer.execute(
            sa.update(FunctionTestCase)
            .where(FunctionTestCase.case_id == "case")
            .values(title="changed")
        )
        await writer.commit()

        with pytest.raises(SourceClosureError, match="concurrent_change"):
            await verify_import_preview(reader, request=request, now=101, **GUARD)
        await reader.rollback()


async def test_verification_keeps_its_source_when_an_upstream_slot_changes(
    sessions, import_targets
):
    async with sessions() as reader, sessions() as writer:
        request = bound_request(await prepare(reader))
        await reader.commit()
        await writer.execute(
            sa.update(AiGenerationStageContent)
            .where(AiGenerationStageContent.stage_id == import_targets.material_stage)
            .values(source_candidate_id=None, content_token="changed-material")
        )
        await writer.commit()

        source, _ = await verify_import_preview(reader, request=request, now=101, **GUARD)
        await reader.rollback()

    assert source.candidate_id == "d"


async def test_target_lock_holds_back_new_suites_until_released(sessions, import_targets):
    async with sessions() as holder, sessions() as inserter:
        await lock_import_target_state(holder, requirement_id="req", kind="function", target_id="")
        started = asyncio.Event()

        async def add_suite():
            started.set()
            await inserter.execute(
                sa.insert(FunctionTestSuite).values(
                    suite_id="new-suite",
                    requirement_id="req",
                    name="new-module",
                    description="",
                )
            )
            await inserter.commit()

        inserting = asyncio.create_task(add_suite())
        await started.wait()
        blocked = not (await asyncio.wait({inserting}, timeout=0.2))[0]
        await holder.commit()
        await asyncio.wait_for(inserting, timeout=10)

    assert blocked


async def test_execute_leaves_nothing_behind_when_recording_receipts_fails(
    sessions, import_targets, monkeypatch
):
    owner = import_targets.owner
    request = await confirmed_request(sessions, owner)
    original = import_module.record_current_import

    async def fail_after_receipts(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError("simulated")

    monkeypatch.setattr(import_module, "record_current_import", fail_after_receipts)
    async with sessions() as session:
        bundle = generation_services(AiGenerateTaskRepository(session))
        with pytest.raises(RuntimeError, match="simulated"):
            await CurrentImportCoordinator(bundle.imports, bundle.api_importer).execute(
                **COORDINATOR, request=request, actor_id=owner, now=101
            )
        await session.commit()
        imports = await session.scalar(sa.select(sa.func.count()).select_from(AiGenerateImport))
        requests = await session.scalar(
            sa.select(sa.func.count()).select_from(AiGenerateImportRequest)
        )
        cases = await session.scalar(sa.select(sa.func.count()).select_from(FunctionTestCase))

    assert imports == 0
    assert requests == 0
    assert cases == 1


async def test_concurrent_executes_of_one_import_apply_it_once_and_replay(sessions, import_targets):
    owner = import_targets.owner
    request = await confirmed_request(sessions, owner)

    results = await asyncio.gather(
        execute(sessions, request, owner), execute(sessions, request, owner)
    )

    async with sessions() as session:
        imports = await session.scalar(sa.select(sa.func.count()).select_from(AiGenerateImport))
        requests = await session.scalar(
            sa.select(sa.func.count()).select_from(AiGenerateImportRequest)
        )
        cases = await session.scalar(sa.select(sa.func.count()).select_from(FunctionTestCase))
    assert sorted(result["replayed"] for result in results) == [False, True]
    assert results[0]["importRecords"] == results[1]["importRecords"]
    assert imports == 2
    assert requests == 1
    assert cases == 2


async def test_receipts_outlive_their_task_and_freeze_the_upstream_outputs(
    sessions, import_targets
):
    owner = import_targets.owner
    request = await confirmed_request(sessions, owner)
    await execute(sessions, request, owner)

    async with sessions() as session:
        await delete_chain_storage_for_task(session, task_id=import_targets.function_task_id)
        await session.execute(
            sa.delete(AiGenerateTask).where(
                AiGenerateTask.task_id == import_targets.function_task_id
            )
        )
        await session.commit()
        receipts = (await session.scalars(sa.select(AiGenerateImport))).all()

    assert len(receipts) == 2
    assert all(item.content == OUTPUT for item in receipts)
    assert all(len(item.source_snapshot_json["upstreamOutputs"]) == 3 for item in receipts)


async def test_target_fingerprint_notices_assertions_added_after_the_lock(sessions, import_targets):
    async with sessions() as holder, sessions() as inserter:
        before = await lock_import_target_state(
            holder, requirement_id="req", kind="api", target_id="api-target"
        )
        started = asyncio.Event()

        async def add_assertion():
            started.set()
            await inserter.execute(
                sa.insert(ApiAssertRule).values(
                    assert_rule_id="new-assert",
                    case_id="api-case",
                    name="status",
                    assert_source="status_code",
                    comparator="eq",
                    expected_value="200",
                    target_expr="",
                    enabled=True,
                    order_no=1,
                )
            )
            await inserter.commit()

        inserting = asyncio.create_task(add_assertion())
        await started.wait()
        blocked = not (await asyncio.wait({inserting}, timeout=0.2))[0]
        await holder.commit()
        await asyncio.wait_for(inserting, timeout=10)
        after = await lock_import_target_state(
            holder, requirement_id="req", kind="api", target_id="api-target"
        )

    assert blocked
    assert after.fingerprint != before.fingerprint
