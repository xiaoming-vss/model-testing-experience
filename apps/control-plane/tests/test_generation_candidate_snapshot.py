"""Worker snapshots contain just the verified selected branch and its material."""

import json
from uuid import uuid4

import pytest
from support.requirement_versions import material_artifact, points_artifact, scope_artifact

from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.schemas.generation_candidates import (
    CandidateRunRequest,
    FrozenCandidateInput,
    FrozenCandidateSource,
    FrozenRootSource,
    FrozenSelectedSource,
    SourceSelection,
)
from testing_agent.services.generation_candidate_snapshot import (
    build_candidate_input_snapshot,
    candidate_request_signature,
)
from testing_agent.services.generation_source_selection import ResolvedRunSources, SelectedContent


def source_fixture():
    material = SelectedContent(
        "requirement_analysis", "extracting_text", json.dumps(material_artifact()), "json"
    )
    analysis = SelectedContent(
        "function", "requirement_analysis", json.dumps(scope_artifact()), "json"
    )
    points = SelectedContent("function", "case_names", json.dumps(points_artifact()), "json")
    records = [
        FrozenCandidateSource(
            requirement_id="req",
            chain_kind=item.chain_kind,
            stage=item.stage,
            candidate_id=key,
            snapshot_id=f"s-{key}",
            content_hash=f"h-{key}",
            basis_hash=f"b-{key}",
        )
        for key, item in (("m", material), ("a", analysis), ("p", points))
    ]
    manifest = FrozenCandidateInput(
        generation_mode="trial",
        lineage_hash="lineage",
        sources=records,
        root_sources=[
            FrozenRootSource(
                snapshot_id="root",
                resource_kind="requirement_document",
                resource_id="req",
                content_hash="root-hash",
            )
        ],
        selected_sources=[
            FrozenSelectedSource(
                chain_kind="function",
                stage="requirement_analysis",
                source_kind="candidate",
                candidate_id="a",
                snapshot_id="s-a",
            ),
            FrozenSelectedSource(
                chain_kind="function",
                stage="case_names",
                source_kind="candidate",
                candidate_id="p",
                snapshot_id="s-p",
            ),
        ],
    )
    request = CandidateRunRequest(
        connection_id="conn",
        generation_mode="trial",
        request_id=uuid4(),
        config_json={"language": "zh"},
        source_selections=[
            SourceSelection(
                chain_kind="function",
                stage="requirement_analysis",
                source_kind="candidate",
                candidate_id="a",
                snapshot_id="s-a",
                expected_candidate_token="token-a",
            ),
            SourceSelection(
                chain_kind="function",
                stage="case_names",
                source_kind="candidate",
                candidate_id="p",
                snapshot_id="s-p",
                expected_candidate_token="token-p",
            ),
        ],
    )
    return request, ResolvedRunSources(manifest, (analysis, points), (material, analysis, points))


def build(request, sources):
    return build_candidate_input_snapshot(
        requirement_id="req",
        kind="function",
        stage="detailed_cases",
        request=request,
        sources=sources,
        source={"requirementId": "req", "name": "task"},
        attachment_hashes={},
    )


def test_snapshot_contains_selected_outputs_and_material_without_mutating_request():
    request, sources = source_fixture()
    snapshot = build(request, sources)
    assert json.loads(snapshot["source"]["sourceContent"]) == material_artifact()
    assert snapshot["source"]["sourceFormat"] == "requirement_understanding_json"
    assert snapshot["config"]["requirementAnalysis"] == scope_artifact()
    assert snapshot["config"]["caseNames"] == points_artifact()
    assert request.config_json == {"language": "zh"}
    assert snapshot["candidateInput"]["lineageHash"] == "lineage"
    assert snapshot["candidateBasisHash"].startswith("sha256:")


def test_request_identity_binds_mode_selection_and_instruction():
    request, sources = source_fixture()
    signature = candidate_request_signature(
        requirement_id="req", kind="function", stage="detailed_cases", request=request
    )
    replay = request.model_copy(update={"request_id": uuid4()})
    assert signature == candidate_request_signature(
        requirement_id="req", kind="function", stage="detailed_cases", request=replay
    )
    changed = request.model_copy(update={"instruction": "different"})
    assert signature != candidate_request_signature(
        requirement_id="req", kind="function", stage="detailed_cases", request=changed
    )
    choice = request.source_selections[0].model_copy(update={"snapshot_id": "different"})
    mismatch = request.model_copy(
        update={"source_selections": [choice, request.source_selections[1]]}
    )
    with pytest.raises(SourceClosureError, match="source_conflict"):
        build(mismatch, sources)
    injected = request.model_copy(update={"config_json": {"caseNames": {"forged": True}}})
    with pytest.raises(SourceClosureError, match="source_conflict"):
        build(injected, sources)
