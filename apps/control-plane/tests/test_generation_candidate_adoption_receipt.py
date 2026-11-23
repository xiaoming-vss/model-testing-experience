"""Adoption receipts make retries safe without restoring newer current state."""

from uuid import uuid4

import pytest
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401
from support.generation_candidate_graph import ROOT
from support.generation_source_seed import seed_graph

from testing_agent.core.errors import AppError
from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationReviewReceipt,
    AiGenerationStageContent,
)
from testing_agent.repositories.generation_candidate_storage import clear_current_if_unchanged
from testing_agent.schemas.generation_candidates import CandidateAdoptRequest
from testing_agent.services.generation_candidate_adoption_receipt import adopt_candidate_once


def prepare(sync):
    graph = seed_graph(sync)
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
    return graph


def request(key):
    return CandidateAdoptRequest(
        action="adopt",
        candidate_id=key,
        expected_candidate_token=f"token-{key}",
        expected_attempt_id=f"attempt-{key}",
        expected_current_token=f"empty-{key}",
        request_id=uuid4(),
    )


async def test_replay_returns_receipt_without_restoring_cleared_current(database):  # noqa: F811
    sync, _, _ = database
    prepare(sync)
    session = AsyncSessionAdapter(sync)
    body = request("m")
    options = dict(
        requirement_id="req",
        kind="requirement_analysis",
        stage="extracting_text",
        request=body,
        actor_id="u",
        current_root_hashes={ROOT.key: ROOT.content_hash},
    )
    first = await adopt_candidate_once(session, **options)
    sync.commit()
    assert not first.replayed
    cleared = await clear_current_if_unchanged(
        session, stage_id="stage-m", expected_content_token=first.content_token
    )
    sync.commit()
    replay = await adopt_candidate_once(session, **{**options, "current_root_hashes": {}})
    assert replay.replayed and replay.content_token == first.content_token
    slot = sync.query(AiGenerationStageContent).filter_by(stage_id="stage-m").one()
    assert slot.source_candidate_id is None and slot.content_token == cleared
    assert sync.query(AiGenerationReviewReceipt).count() == 1
    with pytest.raises(AppError, match="请求标识"):
        await adopt_candidate_once(
            session, **{**options, "request": body.model_copy(update={"comment": "changed"})}
        )
    assert sync.query(AiGenerationReviewReceipt).count() == 1


async def test_failed_adoption_leaves_no_receipt_or_frozen_candidates(database):  # noqa: F811
    sync, _, _ = database
    prepare(sync)
    session = AsyncSessionAdapter(sync)
    body = request("p").model_copy(update={"expected_current_token": "stale"})
    options = dict(
        requirement_id="req",
        kind="function",
        stage="case_names",
        request=body,
        actor_id="u",
        current_root_hashes={ROOT.key: ROOT.content_hash},
    )
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await adopt_candidate_once(session, **options)
    sync.rollback()
    assert sync.query(AiGenerationReviewReceipt).count() == 0
    assert all(candidate.frozen_at is None for candidate in sync.query(AiGenerationCandidate).all())
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await adopt_candidate_once(
            session, **{**options, "request": body.model_copy(update={"continue_after": True})}
        )
    sync.rollback()
    assert sync.query(AiGenerationReviewReceipt).count() == 0
