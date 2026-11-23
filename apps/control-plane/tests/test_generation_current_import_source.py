"""Formal import must use an adopted current leaf and its own frozen sources."""

import pytest
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401
from support.generation_candidate_graph import ROOT, SOURCE_SNAPSHOT, make_record
from support.generation_import_seed import seed_import_graph

from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
)
from testing_agent.services.generation_current_import_source import lock_current_import_source


async def checked(sync, **overrides):
    params = dict(
        requirement_id="req",
        kind="function",
        stage="detailed_cases",
        expected_current_token="current-d",
        current_root_hashes={ROOT.key: ROOT.content_hash},
    )
    return await lock_current_import_source(AsyncSessionAdapter(sync), **{**params, **overrides})


async def test_current_import_checks_full_chain_without_mutating_it(database):  # noqa: F811
    sync, _, _ = database
    seed_import_graph(sync)
    preview = await checked(sync)
    assert preview.candidate_id == "d" and preview.content == "content-d"
    assert preview.confirmed_by == "reviewer" and preview.review_comment == "accepted"
    assert preview.full_lineage_hash != preview.source_lineage_hash
    assert all(item.frozen_at is None for item in sync.query(AiGenerationCandidate).all())
    source = await checked(sync, expected_lineage_hash=preview.full_lineage_hash)
    assert source == preview
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await checked(sync, expected_lineage_hash="different")
    with pytest.raises(SourceClosureError, match="source_stale"):
        await checked(sync, current_root_hashes={ROOT.key: "changed"})
    with pytest.raises(SourceClosureError, match="source_unknown"):
        await checked(sync, kind="requirement_analysis", stage="extracting_text")


async def test_switched_ancestor_does_not_change_frozen_leaf_basis(database):  # noqa: F811
    sync, _, _ = database
    seed_import_graph(sync)
    preview = await checked(sync)
    alternative = make_record("m2", "requirement_analysis", "extracting_text")
    sync.add(
        AiGenerationCandidate(
            candidate_id="m2",
            snapshot_id=alternative.snapshot_id,
            chain_id="material-chain",
            stage_id="stage-m",
            content=alternative.content,
            format=alternative.format,
            candidate_token="token-m2",
            disposition="available",
            generation_mode="trial",
            created_by="u",
            source_manifest_json=alternative.source_manifest,
            source_snapshot_json=SOURCE_SNAPSHOT,
            content_hash=alternative.content_hash,
            basis_hash=alternative.basis_hash,
            lineage_hash=alternative.lineage_hash,
        )
    )
    sync.flush()
    sync.query(AiGenerationStageContent).filter_by(
        stage_id="stage-m"
    ).one().source_candidate_id = "m2"
    sync.flush()
    after = await checked(sync, expected_lineage_hash=preview.full_lineage_hash)
    assert after == preview
    leaf = sync.query(AiGenerationStageContent).filter_by(stage_id="stage-d").one()
    assert leaf.content_token == "current-d" and leaf.source_candidate_id == "d"


async def test_missing_leaf_and_changed_token_do_not_import(database):  # noqa: F811
    sync, _, _ = database
    seed_import_graph(sync)
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await checked(sync, expected_current_token="expired")
    sync.query(AiGenerationStageContent).filter_by(
        stage_id="stage-d"
    ).one().source_candidate_id = None
    sync.flush()
    with pytest.raises(SourceClosureError, match="pending_upstream"):
        await checked(sync)
