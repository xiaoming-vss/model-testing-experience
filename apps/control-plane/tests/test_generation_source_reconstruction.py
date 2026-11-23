"""A frozen manifest must agree with independently loaded source records."""

from copy import deepcopy
from dataclasses import replace

import pytest
from support.generation_candidate_graph import ROOT, fixture_graph, reconstruct

from testing_agent.domain.generation_source_closure import RootSnapshot, SourceClosureError


def test_reconstruction_validates_complete_stored_diamond():
    result = reconstruct(fixture_graph())
    assert {item.candidate_id for item in result.stages} == {"m", "a", "p"}
    assert result.roots == (ROOT,)


def test_missing_forged_or_changed_inputs_do_not_become_valid():
    records = fixture_graph()
    missing = {key: value for key, value in records.items() if key != "m"}
    with pytest.raises(SourceClosureError, match="source_unknown"):
        reconstruct(missing)
    with pytest.raises(SourceClosureError, match="source_unknown"):
        reconstruct({**records, "m": replace(records["m"], content="tampered")})
    with pytest.raises(SourceClosureError, match="source_stale"):
        reconstruct(records, current_root_hashes={ROOT.key: "changed"})
    with pytest.raises(SourceClosureError, match="source_unknown"):
        reconstruct(records, verified_basis_hashes={})
    with pytest.raises(SourceClosureError, match="source_stale"):
        reconstruct(
            records,
            verified_basis_hashes={
                "m": "changed",
                "a": records["a"].basis_hash,
                "p": records["p"].basis_hash,
            },
        )
    with pytest.raises(SourceClosureError, match="source_stale"):
        reconstruct({**records, "m": replace(records["m"], disposition="rejected")})


def test_manifest_must_include_and_match_its_real_ancestors():
    records = fixture_graph()
    manifest = deepcopy(records["p"].source_manifest)
    manifest["sources"][0]["contentHash"] = "forged"
    with pytest.raises(SourceClosureError, match="source_conflict"):
        reconstruct({**records, "p": replace(records["p"], source_manifest=manifest)})
    manifest = deepcopy(records["p"].source_manifest)
    manifest["sources"] = [item for item in manifest["sources"] if item["candidateId"] != "m"]
    with pytest.raises(SourceClosureError, match="source_unknown"):
        reconstruct({**records, "p": replace(records["p"], source_manifest=manifest)})
    with pytest.raises(SourceClosureError, match="source_conflict"):
        reconstruct({**records, "m": replace(records["m"], requirement_id="other")})


def test_conflicting_direct_roots_do_not_silently_overwrite_each_other():
    conflicting = RootSnapshot(ROOT.snapshot_id, ROOT.resource_kind, ROOT.resource_id, "different")
    with pytest.raises(SourceClosureError, match="source_conflict"):
        reconstruct(fixture_graph(), direct_roots=(ROOT, conflicting))
