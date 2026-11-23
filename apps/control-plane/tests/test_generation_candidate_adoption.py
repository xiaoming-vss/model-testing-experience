"""Adoption is a stage-local pointer and only checks the frozen candidate basis."""

from uuid import uuid4

import pytest
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401
from support.generation_candidate_graph import ROOT, SOURCE_SNAPSHOT, make_record
from support.generation_source_seed import seed_graph

from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
)
from testing_agent.schemas.generation_candidates import CandidateAdoptRequest
from testing_agent.services.generation_candidate_adoption import adopt_verified_candidate


def empty_slots(sync, graph):
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


def request(key, token=None):
    return CandidateAdoptRequest(
        action="adopt",
        candidate_id=key,
        expected_candidate_token=f"token-{key}",
        expected_attempt_id=f"attempt-{key}",
        expected_current_token=token or f"empty-{key}",
        request_id=uuid4(),
    )


async def adopt(sync, graph, key, *, token=None):
    record = graph[key]
    return await adopt_verified_candidate(
        AsyncSessionAdapter(sync),
        requirement_id="req",
        kind=record.chain_kind,
        stage=record.stage,
        request=request(key, token),
        actor_id="u",
        current_root_hashes={ROOT.key: ROOT.content_hash},
    )


async def test_adopt_is_independent_of_upstream_order(database):  # noqa: F811
    sync, _, _ = database
    graph = seed_graph(sync)
    empty_slots(sync, graph)
    token = await adopt(sync, graph, "p")
    sync.commit()
    current = sync.query(AiGenerationStageContent).filter_by(stage_id="stage-p").one()
    assert current.source_candidate_id == "p" and current.content_token == token
    assert current.content == "content-p"
    await adopt(sync, graph, "m")
    sync.commit()
    await adopt(sync, graph, "a")
    sync.commit()
    assert sync.query(AiGenerationCandidate).count() == 3


async def test_adoption_rejects_stale_target_and_root(database):  # noqa: F811
    sync, _, _ = database
    graph = seed_graph(sync)
    empty_slots(sync, graph)
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await adopt(sync, graph, "m", token="stale")
    sync.rollback()
    with pytest.raises(SourceClosureError, match="source_stale"):
        await adopt_verified_candidate(
            AsyncSessionAdapter(sync),
            requirement_id="req",
            kind="requirement_analysis",
            stage="extracting_text",
            request=request("m"),
            actor_id="u",
            current_root_hashes={ROOT.key: "changed"},
        )
    sync.rollback()
    assert sync.query(AiGenerationStageContent).filter_by(stage_id="stage-m").one().content is None


async def test_adoption_uses_frozen_basis_after_upstream_switch(database):  # noqa: F811
    sync, _, _ = database
    graph = seed_graph(sync)
    empty_slots(sync, graph)
    await adopt(sync, graph, "m")
    sync.commit()
    await adopt(sync, graph, "a")
    sync.commit()
    other = make_record("m2", "requirement_analysis", "extracting_text")
    sync.add(
        AiGenerationCandidate(
            candidate_id="m2",
            snapshot_id=other.snapshot_id,
            chain_id="material-chain",
            stage_id="stage-m",
            content=other.content,
            format=other.format,
            current_attempt_id="attempt-m2",
            candidate_token="token-m2",
            disposition="available",
            generation_mode="trial",
            created_by="u",
            source_manifest_json=other.source_manifest,
            source_snapshot_json=SOURCE_SNAPSHOT,
            content_hash=other.content_hash,
            basis_hash=other.basis_hash,
            lineage_hash=other.lineage_hash,
        )
    )
    sync.flush()
    graph["m2"] = other
    old_token = (
        sync.query(AiGenerationStageContent).filter_by(stage_id="stage-m").one().content_token
    )
    await adopt(sync, graph, "m2", token=old_token)
    sync.commit()
    token = await adopt(sync, graph, "p")
    sync.commit()
    current = sync.query(AiGenerationStageContent).filter_by(stage_id="stage-p").one()
    assert current.source_candidate_id == "p" and current.content_token == token
    assert current.content == "content-p"
