"""Real MySQL locks and preview bindings protect formal import sources and targets."""

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.generation import generation_services
from support.generation_candidate_graph import ROOT, SOURCE_SNAPSHOT, fixture_graph, make_record
from support.mysql_initialization import mysql, seed_row  # noqa: F401

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


def test_preview_detects_changed_source_and_locks_formal_targets(mysql, monkeypatch):  # noqa: F811
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

    async def exercise():
        engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        common = dict(
            requirement_id="req",
            kind="function",
            stage="detailed_cases",
            actor_id="u",
            current_root_hashes={ROOT.key: ROOT.content_hash},
            secret=SECRET,
        )
        try:
            async with factory() as reader, factory() as writer:
                preview = await prepare_import_preview(
                    reader, current_token="current-d", target_id="", now=100, **common
                )
                started = asyncio.Event()

                async def edit_case():
                    started.set()
                    await writer.execute(
                        sa.update(FunctionTestCase)
                        .where(FunctionTestCase.case_id == "case")
                        .values(title="changed")
                    )
                    await writer.commit()

                task = asyncio.create_task(edit_case())
                await started.wait()
                assert not (await asyncio.wait({task}, timeout=0.2))[0]
                await reader.commit()
                await asyncio.wait_for(task, timeout=10)
                request = CurrentImportRequest(
                    expected_current_token="current-d",
                    expected_lineage_hash=preview.source.full_lineage_hash,
                    preview_token=preview.preview_token,
                    request_id=uuid4(),
                )
                with pytest.raises(SourceClosureError, match="concurrent_change"):
                    await verify_import_preview(reader, request=request, now=101, **common)
                await reader.rollback()
                preview = await prepare_import_preview(
                    reader, current_token="current-d", target_id="", now=100, **common
                )
                await reader.commit()
                request = request.model_copy(
                    update={
                        "expected_lineage_hash": preview.source.full_lineage_hash,
                        "preview_token": preview.preview_token,
                    }
                )
                await writer.execute(
                    sa.update(AiGenerationStageContent)
                    .where(AiGenerationStageContent.stage_id == stage_ids["m"])
                    .values(source_candidate_id=None, content_token="changed-material")
                )
                await writer.commit()
                source, _ = await verify_import_preview(reader, request=request, now=101, **common)
                assert source.candidate_id == "d"
                await reader.rollback()

            async with factory() as holder, factory() as inserter:
                await lock_import_target_state(
                    holder, requirement_id="req", kind="function", target_id=""
                )
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

                task = asyncio.create_task(add_suite())
                await started.wait()
                assert not (await asyncio.wait({task}, timeout=0.2))[0]
                await holder.commit()
                await asyncio.wait_for(task, timeout=10)

            async with factory() as session:
                await session.execute(
                    sa.update(AiGenerationStageContent)
                    .where(AiGenerationStageContent.stage_id == stage_ids["m"])
                    .values(source_candidate_id="m", content_token="restored-material")
                )
                await session.execute(
                    sa.update(FunctionTestCase)
                    .where(FunctionTestCase.case_id == "case")
                    .values(title="existing")
                )
                await session.commit()

            actor = project["user_id"]
            async with factory() as session:
                bundle = generation_services(AiGenerateTaskRepository(session))
                coordinator = CurrentImportCoordinator(bundle.imports, bundle.api_importer)
                actual_preview = await coordinator.preview(
                    requirement_id="req",
                    kind="function",
                    stage="detailed_cases",
                    current_token="current-d",
                    target_id="",
                    actor_id=actor,
                    current_root_hashes={ROOT.key: ROOT.content_hash},
                    secret=SECRET,
                    now=100,
                )
                assert actual_preview.requires_confirmation
                await session.commit()
            actual_request = CurrentImportRequest(
                expected_current_token=actual_preview.current_token,
                expected_lineage_hash=actual_preview.full_lineage_hash,
                preview_token=actual_preview.preview_token,
                request_id=uuid4(),
                confirm_overwrite=True,
            )
            original_record = import_module.record_current_import

            async def fail_after_receipts(*args, **kwargs):
                await original_record(*args, **kwargs)
                raise RuntimeError("simulated")

            monkeypatch.setattr(import_module, "record_current_import", fail_after_receipts)
            async with factory() as session:
                bundle = generation_services(AiGenerateTaskRepository(session))
                coordinator = CurrentImportCoordinator(bundle.imports, bundle.api_importer)
                with pytest.raises(RuntimeError, match="simulated"):
                    await coordinator.execute(
                        requirement_id="req",
                        kind="function",
                        stage="detailed_cases",
                        request=actual_request,
                        actor_id=actor,
                        current_root_hashes={ROOT.key: ROOT.content_hash},
                        secret=SECRET,
                        now=101,
                    )
                await session.commit()
                assert (
                    await session.scalar(sa.select(sa.func.count()).select_from(AiGenerateImport))
                    == 0
                )
                assert (
                    await session.scalar(
                        sa.select(sa.func.count()).select_from(AiGenerateImportRequest)
                    )
                    == 0
                )
                assert (
                    await session.scalar(sa.select(sa.func.count()).select_from(FunctionTestCase))
                    == 1
                )
            monkeypatch.setattr(import_module, "record_current_import", original_record)

            async def submit_same_import():
                async with factory() as session:
                    bundle = generation_services(AiGenerateTaskRepository(session))
                    coordinator = CurrentImportCoordinator(bundle.imports, bundle.api_importer)
                    result = await coordinator.execute(
                        requirement_id="req",
                        kind="function",
                        stage="detailed_cases",
                        request=actual_request,
                        actor_id=actor,
                        current_root_hashes={ROOT.key: ROOT.content_hash},
                        secret=SECRET,
                        now=101,
                    )
                    await session.commit()
                    return result

            results = await asyncio.gather(submit_same_import(), submit_same_import())
            assert sorted(result["replayed"] for result in results) == [False, True]
            assert results[0]["importRecords"] == results[1]["importRecords"]
            async with factory() as session:
                assert (
                    await session.scalar(sa.select(sa.func.count()).select_from(AiGenerateImport))
                    == 2
                )
                assert (
                    await session.scalar(
                        sa.select(sa.func.count()).select_from(AiGenerateImportRequest)
                    )
                    == 1
                )
                assert (
                    await session.scalar(sa.select(sa.func.count()).select_from(FunctionTestCase))
                    == 2
                )
                await delete_chain_storage_for_task(session, task_id=tasks["function"]["task_id"])
                await session.execute(
                    sa.delete(AiGenerateTask).where(
                        AiGenerateTask.task_id == tasks["function"]["task_id"]
                    )
                )
                await session.commit()
                receipts = (await session.scalars(sa.select(AiGenerateImport))).all()
                assert len(receipts) == 2 and all(item.content == OUTPUT for item in receipts)
                assert all(
                    len(item.source_snapshot_json["upstreamOutputs"]) == 3 for item in receipts
                )
            async with factory() as holder, factory() as inserter:
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

                task = asyncio.create_task(add_assertion())
                await started.wait()
                assert not (await asyncio.wait({task}, timeout=0.2))[0]
                await holder.commit()
                await asyncio.wait_for(task, timeout=10)
                after = await lock_import_target_state(
                    holder, requirement_id="req", kind="api", target_id="api-target"
                )
                assert after.fingerprint != before.fingerprint
        finally:
            await engine.dispose()

    asyncio.run(exercise())
