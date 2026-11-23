"""An import preview becomes invalid on frozen source, target, actor or expiry changes."""

from uuid import uuid4

import pytest
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401
from support.generation_candidate_graph import ROOT
from support.generation_import_seed import seed_import_graph

from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
)
from testing_agent.schemas.generation_candidates import CurrentImportRequest
from testing_agent.services.generation_import_guard import (
    prepare_import_preview,
    verify_import_preview,
)

SECRET = "test-only-preview-signing-key-32-bytes"


async def setup_preview(sync):
    seed_import_graph(sync)
    sync.add(FunctionTestSuite(suite_id="suite", requirement_id="req", name="module"))
    sync.flush()
    sync.add(FunctionTestCase(case_id="case", suite_id="suite", title="existing", module="module"))
    sync.commit()
    session = AsyncSessionAdapter(sync)
    preview = await prepare_import_preview(
        session,
        requirement_id="req",
        kind="function",
        stage="detailed_cases",
        current_token="current-d",
        target_id="",
        actor_id="u",
        current_root_hashes={ROOT.key: ROOT.content_hash},
        secret=SECRET,
        now=100,
    )
    sync.commit()
    request = CurrentImportRequest(
        expected_current_token=preview.source.content_token,
        expected_lineage_hash=preview.source.full_lineage_hash,
        preview_token=preview.preview_token,
        request_id=uuid4(),
        target_id="",
        confirm_overwrite=True,
    )
    return session, request, preview


async def verify(session, request, **overrides):
    params = dict(
        requirement_id="req",
        kind="function",
        stage="detailed_cases",
        request=request,
        actor_id="u",
        current_root_hashes={ROOT.key: ROOT.content_hash},
        secret=SECRET,
        now=101,
    )
    return await verify_import_preview(session, **{**params, **overrides})


async def test_preview_rechecks_and_does_not_freeze_candidates(database):  # noqa: F811
    sync, _, _ = database
    session, request, preview = await setup_preview(sync)
    source, target = await verify(session, request)
    assert source == preview.source and target == preview.target
    assert all(candidate.frozen_at is None for candidate in sync.query(AiGenerationCandidate).all())
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await verify(session, request, actor_id="other")
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await verify(session, request, now=700)


async def test_target_change_after_preview_prevents_import(database):  # noqa: F811
    sync, _, _ = database
    session, request, _ = await setup_preview(sync)
    sync.query(FunctionTestCase).filter_by(case_id="case").one().title = "changed"
    sync.commit()
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await verify(session, request)
    assert sync.query(FunctionTestCase).filter_by(case_id="case").one().title == "changed"


async def test_ancestor_current_change_does_not_invalidate_frozen_leaf(database):  # noqa: F811
    sync, _, _ = database
    session, request, preview = await setup_preview(sync)
    sync.query(AiGenerationStageContent).filter_by(
        stage_id="stage-m"
    ).one().source_candidate_id = None
    sync.commit()
    source, target = await verify(session, request)
    assert source == preview.source and target == preview.target
    assert (
        sync.query(AiGenerationStageContent).filter_by(stage_id="stage-d").one().content_token
        == "current-d"
    )
