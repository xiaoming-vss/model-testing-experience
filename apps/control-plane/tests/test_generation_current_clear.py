"""Clearing current is scoped, idempotent and retains candidate snapshots."""

from uuid import uuid4

import pytest
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401
from support.generation_source_seed import seed_graph

from testing_agent.core.errors import AppError
from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationReviewReceipt,
    AiGenerationStageContent,
)
from testing_agent.repositories.generation_candidate_storage import (
    replace_current_if_unchanged,
)
from testing_agent.schemas.generation_candidates import CurrentClearRequest
from testing_agent.services.generation_current_clear import clear_current_once


async def setup_current(sync):
    graph = seed_graph(sync)
    candidate = sync.query(AiGenerationCandidate).filter_by(candidate_id="m").one()
    sync.add(
        AiGenerationStageContent(
            stage_id="stage-m",
            chain_id="material-chain",
            stage="extracting_text",
            content_token="empty",
        )
    )
    sync.commit()
    token = await replace_current_if_unchanged(
        AsyncSessionAdapter(sync),
        stage_id="stage-m",
        expected_content_token="empty",
        candidate_id="m",
        expected_candidate_token="token-m",
        actor_id="u",
        comment="",
    )
    sync.commit()
    return graph, candidate, token


async def test_clear_replay_does_not_clear_a_later_adoption(database):  # noqa: F811
    sync, _, _ = database
    _, candidate, initial = await setup_current(sync)
    session = AsyncSessionAdapter(sync)
    request = CurrentClearRequest(expected_current_token=initial, request_id=uuid4())
    options = dict(
        requirement_id="req",
        kind="requirement_analysis",
        stage="extracting_text",
        request=request,
        actor_id="u",
    )
    cleared = await clear_current_once(session, **options)
    assert not cleared.replayed
    sync.commit()
    new_token = await replace_current_if_unchanged(
        session,
        stage_id="stage-m",
        expected_content_token=cleared.content_token,
        candidate_id="m",
        expected_candidate_token="token-m",
        actor_id="u",
        comment="",
    )
    sync.commit()
    replay = await clear_current_once(session, **options)
    assert replay.replayed
    assert replay.content_token == cleared.content_token
    sync.commit()
    current = sync.query(AiGenerationStageContent).filter_by(stage_id="stage-m").one()
    assert current.source_candidate_id == candidate.candidate_id
    assert current.content_token == new_token
    assert (
        sync.query(AiGenerationCandidate).filter_by(candidate_id="m").one().content == "content-m"
    )
    assert sync.query(AiGenerationReviewReceipt).count() == 1
    with pytest.raises(AppError, match="请求标识"):
        await clear_current_once(
            session,
            **{
                **options,
                "request": request.model_copy(update={"expected_current_token": "changed"}),
            },
        )


async def test_stale_clear_does_not_write_receipt(database):  # noqa: F811
    sync, _, _ = database
    await setup_current(sync)
    session = AsyncSessionAdapter(sync)
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await clear_current_once(
            session,
            requirement_id="req",
            kind="requirement_analysis",
            stage="extracting_text",
            request=CurrentClearRequest(expected_current_token="old", request_id=uuid4()),
            actor_id="u",
        )
    assert sync.query(AiGenerationReviewReceipt).count() == 0
    current = sync.query(AiGenerationStageContent).filter_by(stage_id="stage-m").one()
    assert current.source_candidate_id == "m"
