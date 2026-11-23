"""Only locked, server-loaded candidate records may form a source closure."""

from datetime import UTC, datetime, timedelta

import pytest
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401
from support.generation_candidate_graph import ROOT
from support.generation_source_seed import seed_graph

from testing_agent.domain.generation_root_fingerprints import fingerprint_generation_basis
from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models.generation_candidates import AiGenerationCandidate
from testing_agent.models.stored_file import StoredFile
from testing_agent.services.generation_source_resolution import (
    ResolvedCandidateSelection,
    lock_candidate_source_closure,
)


def selections(graph, wrong_token=False):
    return tuple(
        ResolvedCandidateSelection(
            graph[key].chain_kind,
            graph[key].stage,
            key,
            graph[key].snapshot_id,
            "wrong" if key == "a" and wrong_token else f"token-{key}",
        )
        for key in ("a", "p")
    )


async def test_reachable_sources_are_reconstructed_and_frozen(database):  # noqa: F811
    sync, _, _ = database
    graph = seed_graph(sync)
    result = await lock_candidate_source_closure(
        AsyncSessionAdapter(sync),
        requirement_id="req",
        selections=selections(graph),
        required_stages=frozenset(
            {("function", "requirement_analysis"), ("function", "case_names")}
        ),
        current_root_hashes={ROOT.key: ROOT.content_hash},
    )
    assert {item.candidate_id for item in result.stages} == {"m", "a", "p"}
    assert all(item.frozen_at is not None for item in sync.query(AiGenerationCandidate).all())
    sync.rollback()
    assert all(item.frozen_at is None for item in sync.query(AiGenerationCandidate).all())


async def test_invalid_graph_never_freezes_sources(database):  # noqa: F811
    sync, _, _ = database
    graph = seed_graph(sync)
    base = dict(
        session=AsyncSessionAdapter(sync),
        requirement_id="req",
        selections=selections(graph),
        required_stages=frozenset(
            {("function", "requirement_analysis"), ("function", "case_names")}
        ),
        current_root_hashes={ROOT.key: ROOT.content_hash},
    )
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await lock_candidate_source_closure(
            **{**base, "selections": selections(graph, wrong_token=True)}
        )
    with pytest.raises(SourceClosureError, match="source_stale"):
        await lock_candidate_source_closure(
            **{**base, "current_root_hashes": {ROOT.key: "changed"}}
        )
    candidate = sync.query(AiGenerationCandidate).filter_by(candidate_id="m").one()
    candidate.source_snapshot_json = {"source": {}}
    sync.flush()
    with pytest.raises(SourceClosureError, match="source_unknown"):
        await lock_candidate_source_closure(**base)
    assert all(item.frozen_at is None for item in sync.query(AiGenerationCandidate).all())


async def test_revision_attachment_hash_is_read_from_locked_file_metadata(database):  # noqa: F811
    sync, _, _ = database
    graph = seed_graph(sync)
    candidate = sync.query(AiGenerationCandidate).filter_by(candidate_id="m").one()
    snapshot = {
        "source": {"instruction": "revise"},
        "config": {"revisionAttachments": [{"fileId": "image", "filename": "image.png"}]},
        "revisionInstruction": "revise",
        "currentOutput": "old content",
    }
    candidate.source_snapshot_json = snapshot
    candidate.basis_hash = fingerprint_generation_basis(
        kind="requirement_analysis",
        stage="extracting_text",
        input_snapshot=snapshot,
        roots=(ROOT,),
        lineage_hash=candidate.lineage_hash,
        attachment_hashes={"image": "image-hash"},
    )
    sync.add(
        StoredFile(
            file_id="image",
            project_id="p",
            uploaded_by="u",
            filename="image.png",
            content_type="image/png",
            size=10,
            sha256="image-hash",
            bucket="bucket",
            object_key="image",
            staging_key="",
            status="attached",
            purpose="attachment",
            resource_type="ai_generate_run",
            resource_id="old-attempt",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    sync.commit()
    selection = ResolvedCandidateSelection(
        "requirement_analysis", "extracting_text", "m", graph["m"].snapshot_id, "token-m"
    )
    options = dict(
        session=AsyncSessionAdapter(sync),
        requirement_id="req",
        selections=(selection,),
        required_stages=frozenset({("requirement_analysis", "extracting_text")}),
        current_root_hashes={ROOT.key: ROOT.content_hash},
    )
    result = await lock_candidate_source_closure(**options)
    assert len(result.stages) == 1
    sync.rollback()
    image = sync.query(StoredFile).filter_by(file_id="image").one()
    image.sha256 = "changed"
    sync.flush()
    with pytest.raises(SourceClosureError, match="source_stale"):
        await lock_candidate_source_closure(**options)
