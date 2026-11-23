"""Revision inputs retain their original branch and identify the exact parent."""

from copy import deepcopy
from uuid import uuid4

import pytest
from support.ai_execution import db as db  # noqa: F401
from support.database_read_paths import database  # noqa: F401
from support.generation_candidate_graph import ROOT
from support.generation_source_seed import seed_graph

from testing_agent.domain.generation_root_fingerprints import fingerprint_generation_basis
from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models.generation_candidates import AiGenerationCandidate
from testing_agent.schemas.generation_candidates import CandidateRevisionRequest
from testing_agent.services.generation_revision_snapshot import build_revision_snapshot


def test_revision_snapshot_preserves_inputs_and_records_parent(database):  # noqa: F811
    sync, _, _ = database
    seed_graph(sync)
    parent = sync.query(AiGenerationCandidate).filter_by(candidate_id="p").one()
    parent.current_attempt_id = "attempt-p"
    original = deepcopy(parent.source_snapshot_json)
    request = CandidateRevisionRequest(
        expected_candidate_token=parent.candidate_token,
        expected_attempt_id="attempt-p",
        connection_id="llm",
        instruction="补充边界",
        request_id=uuid4(),
        attachment_file_ids=["image"],
    )
    options = dict(
        candidate=parent,
        kind="function",
        stage="case_names",
        request=request,
        signature="signature",
        attempt_id="revision-attempt",
        actor_id="u",
        attachments=({"fileId": "image", "filename": "image.png", "contentType": "image/png"},),
        attachment_hashes={"image": "digest"},
    )
    snapshot = build_revision_snapshot(**options)
    assert snapshot["candidateProtocol"] == "single-current/2"
    assert (
        snapshot["candidateInput"]["selectedSources"]
        == parent.source_manifest_json["selectedSources"]
    )
    assert snapshot["revisionParent"]["candidateId"] == "p"
    assert snapshot["currentOutput"] == parent.content
    assert snapshot["candidateBasisHash"]
    changed_parent = deepcopy(snapshot)
    changed_parent["revisionParent"]["candidateId"] = "another-candidate"
    assert (
        fingerprint_generation_basis(
            kind="function",
            stage="case_names",
            input_snapshot=changed_parent,
            roots=(ROOT,),
            lineage_hash=parent.lineage_hash,
            attachment_hashes={"image": "digest"},
        )
        != snapshot["candidateBasisHash"]
    )
    assert parent.source_snapshot_json == original
    with pytest.raises(SourceClosureError, match="source_unknown"):
        build_revision_snapshot(**{**options, "attachment_hashes": {}})
    parent.content = "changed"
    with pytest.raises(SourceClosureError, match="source_stale"):
        build_revision_snapshot(**options)
