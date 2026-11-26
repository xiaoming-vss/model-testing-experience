"""Current runs and candidate trials resolve only verified server-side content."""

from copy import deepcopy

import pytest
from support.ai_execution import AsyncSessionAdapter
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401
from support.generation_candidate_graph import ROOT, SOURCE_SNAPSHOT, make_record
from support.generation_source_seed import seed_graph

from testing_agent.domain.generation_root_fingerprints import fingerprint_generation_basis
from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
    RequirementGenerationChain,
)
from testing_agent.schemas.generation_candidates import CandidateRunRequest, SourceSelection
from testing_agent.services.generation_source_selection import resolve_run_sources
from testing_agent.services.generation_ui_candidate_source import read_selected_ui_surface_source


def seed_slots(sync, graph):
    for key, record in graph.items():
        candidate = sync.query(AiGenerationCandidate).filter_by(candidate_id=key).one()
        sync.add(
            AiGenerationStageContent(
                stage_id=candidate.stage_id,
                chain_id=candidate.chain_id,
                stage=record.stage,
                content=candidate.content,
                format=candidate.format,
                context_json=candidate.context_json,
                content_hash=candidate.content_hash,
                basis_hash=candidate.basis_hash,
                content_token=f"current-{key}",
                source_manifest_json=candidate.source_manifest_json,
                source_snapshot_json=candidate.source_snapshot_json,
                lineage_hash=candidate.lineage_hash,
                source_candidate_id=key,
            )
        )
    sync.commit()


def choice(graph, key, mode):
    record = graph[key]
    params = {"chain_kind": record.chain_kind, "stage": record.stage, "source_kind": mode}
    if mode == "current":
        params["expected_current_token"] = f"current-{key}"
    else:
        params.update(
            candidate_id=key,
            snapshot_id=record.snapshot_id,
            expected_candidate_token=f"token-{key}",
        )
    return SourceSelection(**params)


async def resolve(sync, request):
    return await resolve_run_sources(
        AsyncSessionAdapter(sync),
        requirement_id="req",
        kind="function",
        stage="detailed_cases",
        request=request,
        current_root_hashes={ROOT.key: ROOT.content_hash},
    )


async def test_current_uses_verified_chain_and_only_direct_contents(database):  # noqa: F811
    sync, _, _ = database
    graph = seed_graph(sync)
    seed_slots(sync, graph)
    result = await resolve(sync, CandidateRunRequest(connection_id="c"))
    assert {item.stage for item in result.selected_content} == {
        "requirement_analysis",
        "case_names",
    }
    assert {item.content for item in result.selected_content} == {"content-a", "content-p"}
    assert {item.source_kind for item in result.manifest.selected_sources} == {"current"}
    assert len(result.manifest.sources) == 3
    assert all(item.frozen_at for item in sync.query(AiGenerationCandidate).all())


async def test_current_run_can_require_the_exact_upstream_token(database):  # noqa: F811
    sync, _, _ = database
    graph = seed_graph(sync)
    seed_slots(sync, graph)
    required = choice(graph, "p", "current")
    request = CandidateRunRequest(connection_id="c", required_current_source=required)
    result = await resolve(sync, request)
    assert {item.stage for item in result.selected_content} == {
        "requirement_analysis",
        "case_names",
    }
    sync.rollback()
    stale = required.model_copy(update={"expected_current_token": "old"})
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await resolve(sync, request.model_copy(update={"required_current_source": stale}))
    sync.rollback()
    # A token for an unrelated stage cannot silently authorize another source.
    unrelated = choice(graph, "m", "current")
    with pytest.raises(SourceClosureError, match="source_conflict"):
        await resolve(sync, request.model_copy(update={"required_current_source": unrelated}))


async def test_advisory_review_can_guard_continuation_without_becoming_input(database):  # noqa: F811
    sync, _, _ = database
    seed_graph(sync)
    review = make_record("review", "requirement_analysis", "requirement_review")
    sync.add(
        AiGenerationStage(id="stage-review", task_id="material-task", stage="requirement_review")
    )
    sync.flush()
    sync.add(
        AiGenerationCandidate(
            candidate_id="review",
            snapshot_id=review.snapshot_id,
            chain_id="material-chain",
            stage_id="stage-review",
            content=review.content,
            format=review.format,
            candidate_token="review-token",
            disposition="available",
            generation_mode="trial",
            created_by="u",
            source_manifest_json=review.source_manifest,
            source_snapshot_json=SOURCE_SNAPSHOT,
            content_hash=review.content_hash,
            basis_hash=review.basis_hash,
            lineage_hash=review.lineage_hash,
        )
    )
    sync.flush()
    sync.add(
        AiGenerationStageContent(
            stage_id="stage-review",
            chain_id="material-chain",
            stage="requirement_review",
            content=review.content,
            format=review.format,
            content_hash=review.content_hash,
            basis_hash=review.basis_hash,
            lineage_hash=review.lineage_hash,
            source_manifest_json=review.source_manifest,
            source_snapshot_json=SOURCE_SNAPSHOT,
            content_token="review-current",
            source_candidate_id="review",
        )
    )
    sync.commit()
    guard = SourceSelection(
        chain_kind="requirement_analysis",
        stage="requirement_review",
        source_kind="current",
        expected_current_token="review-current",
    )
    request = CandidateRunRequest(connection_id="c", required_current_source=guard)
    session = AsyncSessionAdapter(sync)
    result = await resolve_run_sources(
        session,
        requirement_id="req",
        kind="requirement_analysis",
        stage="extracting_text",
        request=request,
        current_root_hashes={ROOT.key: ROOT.content_hash},
        direct_roots=(ROOT,),
    )
    assert not result.manifest.selected_sources
    sync.rollback()
    guard.expected_current_token = "changed"
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await resolve_run_sources(
            session,
            requirement_id="req",
            kind="requirement_analysis",
            stage="extracting_text",
            request=request,
            current_root_hashes={ROOT.key: ROOT.content_hash},
            direct_roots=(ROOT,),
        )
    sync.rollback()
    guard.expected_current_token = "review-current"
    with pytest.raises(SourceClosureError, match="source_stale"):
        await resolve_run_sources(
            session,
            requirement_id="req",
            kind="requirement_analysis",
            stage="extracting_text",
            request=request,
            current_root_hashes={ROOT.key: "different-document"},
            direct_roots=(ROOT,),
        )


async def test_trial_candidates_do_not_need_current_but_current_choices_do(database):  # noqa: F811
    sync, _, _ = database
    graph = seed_graph(sync)
    trial = CandidateRunRequest(
        connection_id="c",
        generation_mode="trial",
        source_selections=[choice(graph, "a", "candidate"), choice(graph, "p", "candidate")],
    )
    result = await resolve(sync, trial)
    assert {item.source_kind for item in result.manifest.selected_sources} == {"candidate"}
    sync.rollback()
    current = CandidateRunRequest(connection_id="c")
    with pytest.raises(SourceClosureError, match="pending_upstream"):
        await resolve(sync, current)
    seed_slots(sync, graph)
    mixed = CandidateRunRequest(
        connection_id="c",
        generation_mode="trial",
        source_selections=[choice(graph, "a", "current"), choice(graph, "p", "candidate")],
    )
    assert len((await resolve(sync, mixed)).selected_content) == 2
    sync.rollback()
    sync.query(AiGenerationStageContent).filter_by(stage_id="stage-m").delete()
    sync.flush()
    assert len((await resolve(sync, mixed)).selected_content) == 2
    sync.rollback()


async def test_switched_upstream_does_not_block_current_run_and_stale_token_is_rejected(
    database,  # noqa: F811
):
    sync, _, _ = database
    graph = seed_graph(sync)
    seed_slots(sync, graph)
    alternative = make_record("new", "requirement_analysis", "extracting_text")
    sync.add(
        AiGenerationCandidate(
            candidate_id="new",
            snapshot_id=alternative.snapshot_id,
            chain_id="material-chain",
            stage_id="stage-m",
            content=alternative.content,
            format=alternative.format,
            candidate_token="token-new",
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
    slot = sync.query(AiGenerationStageContent).filter_by(stage_id="stage-m").one()
    slot.source_candidate_id = "new"
    slot.content_token = "current-new"
    sync.commit()
    result = await resolve(sync, CandidateRunRequest(connection_id="c"))
    assert {item.content for item in result.selected_content} == {"content-a", "content-p"}
    assert len(result.manifest.sources) == 3
    sync.rollback()
    assert all(item.frozen_at is None for item in sync.query(AiGenerationCandidate).all())
    trial = CandidateRunRequest(
        connection_id="c",
        generation_mode="trial",
        source_selections=[choice(graph, "a", "candidate"), choice(graph, "p", "candidate")],
    )
    assert len((await resolve(sync, trial)).selected_content) == 2
    sync.rollback()
    stale = choice(graph, "a", "current").model_copy(update={"expected_current_token": "old"})
    mixed = CandidateRunRequest(
        connection_id="c",
        generation_mode="trial",
        source_selections=[stale, choice(graph, "p", "candidate")],
    )
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await resolve(sync, mixed)


async def test_trial_cannot_mix_different_analysis_branches(database):  # noqa: F811
    sync, _, _ = database
    graph = seed_graph(sync)
    alternative = make_record(
        "other-analysis",
        "function",
        "requirement_analysis",
        parents=(graph["m"],),
        ancestors=(graph["m"],),
    )
    sync.add(
        AiGenerationCandidate(
            candidate_id=alternative.candidate_id,
            snapshot_id=alternative.snapshot_id,
            chain_id="function-chain",
            stage_id="stage-a",
            content=alternative.content,
            format=alternative.format,
            candidate_token="token-other-analysis",
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
    sync.commit()
    graph["other-analysis"] = alternative
    request = CandidateRunRequest(
        connection_id="c",
        generation_mode="trial",
        source_selections=[
            choice(graph, "other-analysis", "candidate"),
            choice(graph, "p", "candidate"),
        ],
    )
    with pytest.raises(SourceClosureError, match="source_conflict"):
        await resolve(sync, request)
    sync.rollback()
    assert all(item.frozen_at is None for item in sync.query(AiGenerationCandidate).all())


async def test_revision_source_checks_same_stage_parent_and_its_frozen_inputs(database):  # noqa: F811
    sync, _, _ = database
    graph = seed_graph(sync)
    parent = sync.query(AiGenerationCandidate).filter_by(candidate_id="p").one()
    parent.current_attempt_id = "attempt-p"
    revised = make_record(
        "p2", "function", "case_names", parents=(graph["a"],), ancestors=(graph["m"], graph["a"])
    )
    snapshot = deepcopy(SOURCE_SNAPSHOT)
    snapshot.update(
        {
            "candidateProtocol": "single-current/2",
            "revisionAttemptId": "revision-p2",
            "revisionActorId": "u",
            "currentOutput": parent.content,
            "revisionInstruction": "补充边界",
            "revisionParent": {
                "candidateId": "p",
                "snapshotId": parent.snapshot_id,
                "candidateToken": parent.candidate_token,
                "attemptId": parent.current_attempt_id,
                "contentHash": parent.content_hash,
            },
        }
    )
    basis = fingerprint_generation_basis(
        kind="function",
        stage="case_names",
        input_snapshot=snapshot,
        roots=(ROOT,),
        lineage_hash=revised.lineage_hash,
        attachment_hashes={},
    )
    sync.add(
        AiGenerationCandidate(
            candidate_id="p2",
            snapshot_id=revised.snapshot_id,
            chain_id="function-chain",
            stage_id="stage-p",
            derived_from_candidate_id="p",
            content=revised.content,
            format=revised.format,
            candidate_token="token-p2",
            disposition="available",
            generation_mode="trial",
            created_by="u",
            source_manifest_json=revised.source_manifest,
            source_snapshot_json=snapshot,
            content_hash=revised.content_hash,
            basis_hash=basis,
            lineage_hash=revised.lineage_hash,
        )
    )
    sync.commit()
    graph["p2"] = revised
    request = CandidateRunRequest(
        connection_id="c",
        generation_mode="trial",
        source_selections=[choice(graph, "a", "candidate"), choice(graph, "p2", "candidate")],
    )
    assert len((await resolve(sync, request)).selected_content) == 2
    sync.rollback()
    parent = sync.query(AiGenerationCandidate).filter_by(candidate_id="p").one()
    parent.disposition = "rejected"
    sync.flush()
    with pytest.raises(SourceClosureError, match="source_stale"):
        await resolve(sync, request)
    sync.rollback()
    parent = sync.query(AiGenerationCandidate).filter_by(candidate_id="p").one()
    parent.content = "tampered"
    sync.flush()
    with pytest.raises(SourceClosureError, match="source_stale"):
        await resolve(sync, request)


async def test_ui_surface_source_selection_checks_candidate_and_current_tokens(database):  # noqa: F811
    sync, _, _ = database
    graph = seed_graph(sync)
    sync.query(AiGenerateTask).filter_by(task_id="task").one().task_type = "ui_case_generate"
    sync.query(RequirementGenerationChain).filter_by(chain_id="function-chain").one().kind = "ui"
    sync.query(AiGenerationStage).filter_by(id="stage-a").one().stage = "ui_surface"
    candidate = sync.query(AiGenerationCandidate).filter_by(candidate_id="a").one()
    sync.commit()
    session = AsyncSessionAdapter(sync)
    current = CandidateRunRequest(connection_id="c")
    with pytest.raises(SourceClosureError, match="pending_upstream"):
        await read_selected_ui_surface_source(session, requirement_id="req", request=current)
    choice = SourceSelection(
        chain_kind="ui",
        stage="ui_surface",
        source_kind="candidate",
        candidate_id="a",
        snapshot_id=graph["a"].snapshot_id,
        expected_candidate_token="token-a",
    )
    trial = CandidateRunRequest(
        connection_id="c", generation_mode="trial", source_selections=[choice]
    )
    selected = await read_selected_ui_surface_source(session, requirement_id="req", request=trial)
    assert selected.candidate_id == "a" and selected.source == SOURCE_SNAPSHOT["source"]
    selected.source["instruction"] = "changed"
    assert candidate.source_snapshot_json == SOURCE_SNAPSHOT
    stale = choice.model_copy(update={"expected_candidate_token": "stale"})
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await read_selected_ui_surface_source(
            session,
            requirement_id="req",
            request=trial.model_copy(update={"source_selections": [stale]}),
        )
    sync.add(
        AiGenerationStageContent(
            stage_id="stage-a",
            chain_id="function-chain",
            stage="ui_surface",
            content_token="current-a",
            source_candidate_id="a",
        )
    )
    sync.commit()
    selected = await read_selected_ui_surface_source(session, requirement_id="req", request=current)
    assert selected.current_token == "current-a"
    stale_current = SourceSelection(
        chain_kind="ui", stage="ui_surface", source_kind="current", expected_current_token="old"
    )
    with pytest.raises(SourceClosureError, match="concurrent_change"):
        await read_selected_ui_surface_source(
            session,
            requirement_id="req",
            request=trial.model_copy(update={"source_selections": [stale_current]}),
        )
