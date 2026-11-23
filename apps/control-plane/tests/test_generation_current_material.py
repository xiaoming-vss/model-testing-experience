"""Auxiliary material input uses the current, source-verified candidate."""

from dataclasses import replace

import pytest
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401
from support.generation_candidate_graph import ROOT
from support.generation_source_seed import seed_graph

from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
)
from testing_agent.services.generation_current_material import lock_current_material


def add_material_slot(sync):
    candidate = sync.query(AiGenerationCandidate).filter_by(candidate_id="m").one()
    sync.add(
        AiGenerationStageContent(
            stage_id=candidate.stage_id,
            chain_id=candidate.chain_id,
            stage="extracting_text",
            content=candidate.content,
            format=candidate.format,
            context_json=candidate.context_json,
            content_hash=candidate.content_hash,
            basis_hash=candidate.basis_hash,
            content_token="current-m",
            source_manifest_json=candidate.source_manifest_json,
            source_snapshot_json=candidate.source_snapshot_json,
            lineage_hash=candidate.lineage_hash,
            source_candidate_id=candidate.candidate_id,
        )
    )
    sync.commit()


async def test_current_material_is_rechecked_and_frozen_only_at_dispatch(database):  # noqa: F811
    sync, _, _ = database
    seed_graph(sync)
    add_material_slot(sync)
    session = AsyncSessionAdapter(sync)
    prepared = await lock_current_material(
        session, requirement_id="req", document_root=ROOT, freeze=False
    )
    assert prepared.candidate_id == "m" and prepared.content == "content-m"
    assert sync.query(AiGenerationCandidate).filter_by(candidate_id="m").one().frozen_at is None
    sync.rollback()
    result = await lock_current_material(
        session, requirement_id="req", document_root=ROOT, freeze=True, expected=prepared
    )
    assert result == prepared
    assert sync.query(AiGenerationCandidate).filter_by(candidate_id="m").one().frozen_at
    sync.rollback()
    slot = sync.query(AiGenerationStageContent).filter_by(stage_id="stage-m").one()
    slot.content_token = "changed"
    sync.commit()
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await lock_current_material(
            session, requirement_id="req", document_root=ROOT, freeze=True, expected=prepared
        )
    sync.rollback()
    assert sync.query(AiGenerationCandidate).filter_by(candidate_id="m").one().frozen_at is None


async def test_missing_stale_or_tampered_material_is_rejected(database):  # noqa: F811
    sync, _, _ = database
    seed_graph(sync)
    session = AsyncSessionAdapter(sync)
    with pytest.raises(SourceClosureError, match="pending_upstream"):
        await lock_current_material(session, requirement_id="req", document_root=ROOT, freeze=False)
    sync.rollback()
    add_material_slot(sync)
    with pytest.raises(SourceClosureError, match="source_stale"):
        await lock_current_material(
            session,
            requirement_id="req",
            document_root=replace(ROOT, content_hash="changed"),
            freeze=False,
        )
    sync.rollback()
    slot = sync.query(AiGenerationStageContent).filter_by(stage_id="stage-m").one()
    slot.content = "tampered"
    sync.commit()
    with pytest.raises(SourceClosureError, match="source_stale"):
        await lock_current_material(session, requirement_id="req", document_root=ROOT, freeze=False)
