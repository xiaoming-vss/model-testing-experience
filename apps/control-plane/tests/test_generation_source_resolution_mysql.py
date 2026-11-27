"""MySQL source locking rejects snapshots changed after discovery."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from support.generation_candidate_graph import ROOT, SOURCE_SNAPSHOT, fixture_graph
from support.mysql_initialization import async_sessions, mysql, seed_row  # noqa: F401

from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models import AiGenerationCandidate, Base
from testing_agent.models.generation_candidates import AiGenerationStageContent
from testing_agent.schemas.generation_candidates import CandidateAdoptRequest, CandidateRunRequest
from testing_agent.services import generation_source_resolution as resolution
from testing_agent.services import generation_source_selection as selection
from testing_agent.services.generation_candidate_adoption import adopt_verified_candidate
from testing_agent.services.generation_source_resolution import (
    ResolvedCandidateSelection,
    lock_candidate_source_closure,
)


def test_source_changes_between_discovery_and_lock_are_rejected(mysql, monkeypatch):  # noqa: F811
    tables = Base.metadata.tables
    graph = fixture_graph()
    with mysql.begin() as connection:
        project = seed_row(connection, tables["projects"])
        sprint = seed_row(connection, tables["sprints"], {"project_id": project["project_id"]})
        requirement = seed_row(
            connection,
            tables["requirements"],
            {"requirement_id": "req", "sprint_id": sprint["sprint_id"]},
        )
        scope = {
            "project_id": project["project_id"],
            "sprint_id": sprint["sprint_id"],
            "requirement_id": "req",
        }
        material_task = seed_row(
            connection, tables["ai_generate_tasks"], {**scope, "task_type": "requirement_analysis"}
        )
        function_task = seed_row(
            connection,
            tables["ai_generate_tasks"],
            {**scope, "task_type": "functional_case_generate"},
        )
        material_chain = seed_row(
            connection,
            tables["requirement_generation_chains"],
            {
                "requirement_id": requirement["requirement_id"],
                "task_id": material_task["task_id"],
                "kind": "requirement_analysis",
            },
        )
        function_chain = seed_row(
            connection,
            tables["requirement_generation_chains"],
            {
                "requirement_id": requirement["requirement_id"],
                "task_id": function_task["task_id"],
                "kind": "function",
            },
        )
        for key, record in graph.items():
            task = material_task if key == "m" else function_task
            chain = material_chain if key == "m" else function_chain
            stage = seed_row(
                connection,
                tables["ai_generation_stages"],
                {"task_id": task["task_id"], "stage": record.stage},
            )
            seed_row(
                connection,
                tables["ai_generation_candidates"],
                {
                    "candidate_id": key,
                    "snapshot_id": record.snapshot_id,
                    "chain_id": chain["chain_id"],
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
                    "stage_id": stage["id"],
                    "chain_id": chain["chain_id"],
                    "stage": record.stage,
                    "content": record.content,
                    "format": record.format,
                    "content_hash": record.content_hash,
                    "basis_hash": record.basis_hash,
                    "lineage_hash": record.lineage_hash,
                    "source_manifest_json": record.source_manifest,
                    "source_snapshot_json": SOURCE_SNAPSHOT,
                    "source_candidate_id": key,
                    "content_token": f"current-{key}",
                },
            )
    selections = tuple(
        ResolvedCandidateSelection(
            graph[key].chain_kind, graph[key].stage, key, graph[key].snapshot_id, f"token-{key}"
        )
        for key in ("a", "p")
    )
    options = dict(
        requirement_id="req",
        selections=selections,
        required_stages=frozenset(
            {("function", "requirement_analysis"), ("function", "case_names")}
        ),
        current_root_hashes={ROOT.key: ROOT.content_hash},
    )

    async def exercise():
        engine, factory = async_sessions(mysql)
        discovered = asyncio.Event()
        original = resolution._project

        def signal(candidate, chain, stage):
            result = original(candidate, chain, stage)
            if candidate.candidate_id == "m":
                discovered.set()
            return result

        try:
            async with factory() as session:
                closure = await lock_candidate_source_closure(session, **options)
                assert len(closure.stages) == 3
                await session.rollback()
            monkeypatch.setattr(resolution, "_project", signal)
            async with factory() as editor, factory() as reader:
                await editor.scalar(
                    sa.select(AiGenerationCandidate)
                    .where(AiGenerationCandidate.candidate_id == "m")
                    .with_for_update()
                )
                reading = asyncio.create_task(lock_candidate_source_closure(reader, **options))
                await asyncio.wait_for(discovered.wait(), timeout=10)
                await editor.execute(
                    sa.update(AiGenerationCandidate)
                    .where(AiGenerationCandidate.candidate_id == "m")
                    .values(candidate_token="changed-token")
                )
                await editor.commit()
                with pytest.raises(SourceClosureError, match="concurrent_change"):
                    await asyncio.wait_for(reading, timeout=10)
                await reader.rollback()
        finally:
            await engine.dispose()

    asyncio.run(exercise())
    with mysql.connect() as connection:
        candidate = tables["ai_generation_candidates"]
        rows = connection.execute(sa.select(candidate.c.candidate_id, candidate.c.frozen_at)).all()
        assert len(rows) == 3 and all(row.frozen_at is None for row in rows)

    async def test_current_slot_race():
        engine, factory = async_sessions(mysql)
        loaded = asyncio.Event()
        original = selection.lock_candidate_source_closure

        async def signal(*args, **kwargs):
            result = await original(*args, **kwargs)
            loaded.set()
            return result

        monkeypatch.setattr(selection, "lock_candidate_source_closure", signal)
        try:
            async with factory() as editor, factory() as reader:
                await editor.scalar(
                    sa.select(AiGenerationStageContent)
                    .where(AiGenerationStageContent.source_candidate_id == "a")
                    .with_for_update()
                )
                reading = asyncio.create_task(
                    selection.resolve_run_sources(
                        reader,
                        requirement_id="req",
                        kind="function",
                        stage="detailed_cases",
                        request=CandidateRunRequest(connection_id="connection"),
                        current_root_hashes={ROOT.key: ROOT.content_hash},
                    )
                )
                await asyncio.wait_for(loaded.wait(), timeout=10)
                await editor.execute(
                    sa.update(AiGenerationStageContent)
                    .where(AiGenerationStageContent.source_candidate_id == "a")
                    .values(content_token="changed-token")
                )
                await editor.commit()
                with pytest.raises(SourceClosureError, match="concurrent_change"):
                    await asyncio.wait_for(reading, timeout=10)
                await reader.rollback()
        finally:
            await engine.dispose()

    asyncio.run(test_current_slot_race())

    with mysql.begin() as connection:
        connection.execute(
            sa.update(tables["ai_generation_candidates"])
            .where(tables["ai_generation_candidates"].c.candidate_id == "a")
            .values(current_attempt_id="attempt-a")
        )

    async def test_adoption_race():
        engine, factory = async_sessions(mysql)

        async def run():
            async with factory() as session:
                try:
                    token = await adopt_verified_candidate(
                        session,
                        requirement_id="req",
                        kind="function",
                        stage="requirement_analysis",
                        request=CandidateAdoptRequest(
                            action="adopt",
                            candidate_id="a",
                            expected_candidate_token="token-a",
                            expected_attempt_id="attempt-a",
                            expected_current_token="changed-token",
                            request_id=uuid4(),
                        ),
                        actor_id="u",
                        current_root_hashes={ROOT.key: ROOT.content_hash},
                    )
                    await session.commit()
                    return token
                except SourceClosureError as exc:
                    await session.rollback()
                    return exc.reason

        try:
            results = await asyncio.gather(run(), run())
            assert results.count("concurrent_change") == 1
            assert len([item for item in results if item != "concurrent_change"]) == 1
        finally:
            await engine.dispose()

    asyncio.run(test_adoption_race())
