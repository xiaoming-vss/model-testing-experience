"""Candidate branches must have complete, mutually consistent frozen sources."""

from dataclasses import replace

import pytest

from testing_agent.domain.generation_source_closure import (
    RootSnapshot,
    SourceClosureError,
    StageSnapshot,
    resolve_source_closure,
)

ROOT = RootSnapshot("doc-snapshot", "requirement_document", "req", "doc-hash")
MATERIAL = StageSnapshot(
    "req",
    "requirement_analysis",
    "extracting_text",
    "material",
    "m",
    "same-content",
    "same-basis",
    root_snapshot_ids=("doc-snapshot",),
)
ANALYSIS_A = StageSnapshot(
    "req",
    "function",
    "requirement_analysis",
    "analysis-a",
    "a",
    "same-content",
    "same-basis",
    parent_snapshot_ids=("m",),
)
ANALYSIS_B = replace(ANALYSIS_A, candidate_id="analysis-b", snapshot_id="b")
POINTS_A = StageSnapshot(
    "req",
    "function",
    "case_names",
    "points-a",
    "pa",
    "points",
    "basis",
    parent_snapshot_ids=("a",),
)
POINTS_B = replace(POINTS_A, candidate_id="points-b", snapshot_id="pb", parent_snapshot_ids=("b",))
REQUIRED = frozenset({("function", "requirement_analysis"), ("function", "case_names")})


def resolve(selected=("a", "pa"), nodes=(MATERIAL, ANALYSIS_A, POINTS_A), **kwargs):
    return resolve_source_closure(
        requirement_id="req",
        selected_snapshot_ids=selected,
        required_stages=REQUIRED,
        stage_snapshots=nodes,
        root_snapshots=(ROOT,),
        current_root_hashes=kwargs.pop("current_root_hashes", {ROOT.key: ROOT.content_hash}),
        **kwargs,
    )


def test_mixed_branch_is_rejected_even_if_analyses_have_same_content():
    with pytest.raises(SourceClosureError, match="source_conflict"):
        resolve(("a", "pb"), (MATERIAL, ANALYSIS_A, ANALYSIS_B, POINTS_B))


def test_detailed_cases_can_freeze_history_but_must_share_its_material():
    relation = StageSnapshot(
        "req",
        "requirement_analysis",
        "historical_requirement_relations",
        "relation",
        "r",
        "history-content",
        "history-basis",
        parent_snapshot_ids=("m",),
    )
    history = replace(
        relation,
        stage="historical_test_case_verification",
        candidate_id="verification",
        snapshot_id="h",
        parent_snapshot_ids=("r",),
    )
    complete = StageSnapshot(
        "req",
        "function",
        "detailed_cases",
        "complete",
        "c",
        "cases",
        "basis",
        parent_snapshot_ids=("a", "pa", "h"),
    )
    nodes = (MATERIAL, ANALYSIS_A, POINTS_A, relation, history, complete)

    def selected(*extras):
        return resolve_source_closure(
            requirement_id="req",
            selected_snapshot_ids=("c",),
            required_stages=frozenset({("function", "detailed_cases")}),
            stage_snapshots=(*nodes, *extras) if extras else nodes,
            root_snapshots=(ROOT,),
            current_root_hashes={ROOT.key: ROOT.content_hash},
        )

    assert history in selected().stages
    mixed_material = replace(MATERIAL, candidate_id="material-b", snapshot_id="m2")
    nodes = (
        MATERIAL,
        ANALYSIS_A,
        POINTS_A,
        replace(relation, parent_snapshot_ids=("m2",)),
        history,
        complete,
    )
    with pytest.raises(SourceClosureError, match="source_conflict"):
        selected(mixed_material)


def test_complete_branch_is_stable_across_order_and_duplicates():
    closure = resolve()
    reordered = resolve(("pa", "a"), (POINTS_A, MATERIAL, ANALYSIS_A))
    assert closure.lineage_hash == reordered.lineage_hash
    assert (
        closure.lineage_hash
        == resolve(nodes=(MATERIAL, ANALYSIS_A, POINTS_A, MATERIAL)).lineage_hash
    )
    assert len(closure.stages) == 3 and len(closure.roots) == 1


def test_missing_ancestor_or_input_is_unknown_and_changed_root_is_stale():
    with pytest.raises(SourceClosureError, match="source_unknown"):
        resolve(nodes=(ANALYSIS_A, POINTS_A))
    with pytest.raises(SourceClosureError, match="source_unknown"):
        resolve(current_root_hashes={})
    with pytest.raises(SourceClosureError, match="source_stale"):
        resolve(current_root_hashes={ROOT.key: "changed"})
    with pytest.raises(SourceClosureError, match="source_unknown"):
        resolve(nodes=(replace(MATERIAL, root_snapshot_ids=()), ANALYSIS_A, POINTS_A))


def test_rejected_source_cross_requirement_and_cycles_do_not_pass():
    with pytest.raises(SourceClosureError, match="source_stale"):
        resolve(nodes=(MATERIAL, replace(ANALYSIS_A, disposition="rejected"), POINTS_A))
    with pytest.raises(SourceClosureError, match="source_conflict"):
        resolve(nodes=(MATERIAL, replace(ANALYSIS_A, requirement_id="other"), POINTS_A))
    cyclic_material = replace(MATERIAL, parent_snapshot_ids=("m",))
    with pytest.raises(SourceClosureError, match="source_conflict"):
        resolve(nodes=(cyclic_material, ANALYSIS_A, POINTS_A))


def test_ui_sources_must_share_batch():
    surface = StageSnapshot(
        "req",
        "ui",
        "ui_surface",
        "surface",
        "surface-s",
        "surface-h",
        "basis",
        root_snapshot_ids=("doc-snapshot",),
        source_batch_id="batch-a",
    )
    design = StageSnapshot(
        "req",
        "ui",
        "ui_design",
        "design",
        "design-s",
        "design-h",
        "basis",
        parent_snapshot_ids=("surface-s",),
        source_batch_id="batch-b",
    )
    with pytest.raises(SourceClosureError, match="source_conflict"):
        resolve_source_closure(
            requirement_id="req",
            selected_snapshot_ids=("surface-s", "design-s"),
            required_stages=frozenset({surface.key, design.key}),
            stage_snapshots=(surface, design),
            root_snapshots=(ROOT,),
            current_root_hashes={ROOT.key: ROOT.content_hash},
        )


def test_direct_root_selection_can_start_a_root_stage():
    closure = resolve_source_closure(
        requirement_id="req",
        selected_snapshot_ids=(),
        required_stages=frozenset(),
        stage_snapshots=(),
        root_snapshots=(ROOT,),
        current_root_hashes={ROOT.key: ROOT.content_hash},
        selected_root_ids=(ROOT.snapshot_id,),
    )
    assert closure.stages == () and closure.roots == (ROOT,)
