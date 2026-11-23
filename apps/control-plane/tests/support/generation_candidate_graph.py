"""A frozen manifest must agree with independently loaded source records."""

from testing_agent.domain.generation_content_hash import generation_content_hash
from testing_agent.domain.generation_root_fingerprints import fingerprint_generation_basis
from testing_agent.domain.generation_source_closure import (
    RootSnapshot,
    StageSnapshot,
    resolve_source_closure,
)
from testing_agent.services.generation_source_reconstruction import (
    StoredCandidateSource,
    reconstruct_source_closure,
)

ROOT = RootSnapshot("root", "requirement_document", "req", "document-hash")
ROOT_JSON = {
    "snapshotId": "root",
    "resourceKind": "requirement_document",
    "resourceId": "req",
    "contentHash": "document-hash",
    "sourceBatchId": None,
}
SOURCE_SNAPSHOT = {"source": {"instruction": ""}, "config": {}}


def node(record):
    manifest = record.source_manifest
    return StageSnapshot(
        record.requirement_id,
        record.chain_kind,
        record.stage,
        record.candidate_id,
        record.snapshot_id,
        record.content_hash,
        record.basis_hash,
        tuple(item["snapshotId"] for item in manifest["selectedSources"]),
        tuple(root["snapshotId"] for root in manifest["rootSources"]),
    )


def frozen(record):
    item = node(record)
    return {
        "requirementId": item.requirement_id,
        "chainKind": item.chain_kind,
        "stage": item.stage,
        "sourceKind": "candidate",
        "candidateId": item.candidate_id,
        "snapshotId": item.snapshot_id,
        "contentHash": item.content_hash,
        "basisHash": item.basis_hash,
        "parentSnapshotIds": list(item.parent_snapshot_ids),
        "rootSnapshotIds": list(item.root_snapshot_ids),
        "sourceBatchId": item.source_batch_id,
    }


def make_record(candidate_id, kind, stage, *, parents=(), ancestors=()):
    required = frozenset((parent.chain_kind, parent.stage) for parent in parents)
    closure = resolve_source_closure(
        requirement_id="req",
        selected_snapshot_ids=tuple(parent.snapshot_id for parent in parents),
        required_stages=required,
        stage_snapshots=tuple(node(item) for item in ancestors),
        root_snapshots=(ROOT,),
        current_root_hashes={ROOT.key: ROOT.content_hash},
        selected_root_ids=(ROOT.snapshot_id,),
    )
    content = f"content-{candidate_id}"
    basis_hash = fingerprint_generation_basis(
        kind=kind,
        stage=stage,
        input_snapshot=SOURCE_SNAPSHOT,
        roots=(ROOT,),
        lineage_hash=closure.lineage_hash,
        attachment_hashes={},
    )
    manifest = {
        "generationMode": "trial",
        "lineageHash": closure.lineage_hash,
        "sources": [frozen(item) for item in ancestors],
        "rootSources": [ROOT_JSON],
        "selectedSources": [
            {
                "chainKind": item.chain_kind,
                "stage": item.stage,
                "sourceKind": "candidate",
                "candidateId": item.candidate_id,
                "snapshotId": item.snapshot_id,
            }
            for item in parents
        ],
    }
    return StoredCandidateSource(
        "req",
        kind,
        stage,
        candidate_id,
        f"snapshot-{candidate_id}",
        content,
        "text",
        generation_content_hash(content, "text"),
        basis_hash,
        closure.lineage_hash,
        "available",
        None,
        manifest,
    )


def fixture_graph():
    material = make_record("m", "requirement_analysis", "extracting_text")
    analysis = make_record(
        "a", "function", "requirement_analysis", parents=(material,), ancestors=(material,)
    )
    points = make_record(
        "p", "function", "case_names", parents=(analysis,), ancestors=(material, analysis)
    )
    return {item.candidate_id: item for item in (material, analysis, points)}


def reconstruct(records, **kwargs):
    return reconstruct_source_closure(
        requirement_id="req",
        selected_candidate_ids=("a", "p"),
        required_stages=frozenset(
            {("function", "requirement_analysis"), ("function", "case_names")}
        ),
        stored_candidates=records,
        current_root_hashes=kwargs.pop("current_root_hashes", {ROOT.key: ROOT.content_hash}),
        verified_basis_hashes=kwargs.pop(
            "verified_basis_hashes", {key: item.basis_hash for key, item in records.items()}
        ),
        **kwargs,
    )
