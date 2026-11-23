"""Validate a server-resolved frozen source graph for one requirement.

This module does not fetch, authorize, or lock sources. Its caller must load
all nodes and current root fingerprints from trusted storage in one correctly
locked transaction; client-supplied graph content is not authoritative.
"""

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from testing_agent.domain.generation_chain import kind_for_stage, stage_names, upstream_stages

StageKey = tuple[str, str]
RootKey = tuple[str, str]
BlockReason = Literal[
    "source_unknown",
    "source_conflict",
    "source_stale",
    "source_mismatch",
    "pending_upstream",
    "concurrent_change",
]


class SourceClosureError(ValueError):
    def __init__(self, reason: BlockReason) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class StageSnapshot:
    requirement_id: str
    chain_kind: str
    stage: str
    candidate_id: str
    snapshot_id: str
    content_hash: str
    basis_hash: str
    parent_snapshot_ids: tuple[str, ...] = ()
    root_snapshot_ids: tuple[str, ...] = ()
    source_batch_id: str | None = None
    disposition: str = "available"

    @property
    def key(self) -> StageKey:
        return self.chain_kind, self.stage


@dataclass(frozen=True)
class RootSnapshot:
    snapshot_id: str
    resource_kind: str
    resource_id: str
    content_hash: str
    source_batch_id: str | None = None

    @property
    def key(self) -> RootKey:
        return self.resource_kind, self.resource_id


@dataclass(frozen=True)
class SourceClosure:
    lineage_hash: str
    stages: tuple[StageSnapshot, ...]
    roots: tuple[RootSnapshot, ...]


def resolve_source_closure(
    *,
    requirement_id: str,
    selected_snapshot_ids: tuple[str, ...],
    required_stages: frozenset[StageKey],
    stage_snapshots: tuple[StageSnapshot, ...],
    root_snapshots: tuple[RootSnapshot, ...],
    current_root_hashes: dict[RootKey, str],
    selected_root_ids: tuple[str, ...] = (),
) -> SourceClosure:
    """Resolve selected snapshots, validate their ancestry and compute its hash.

    ``current_root_hashes`` represents the caller's authoritative checks for
    inputs consumed by this run. For a pinned repository, it must represent the
    explicitly selected pin rather than an implicit fetch of the latest branch.
    """
    nodes: dict[str, StageSnapshot] = {}
    roots: dict[str, RootSnapshot] = {}
    for node in stage_snapshots:
        if node.snapshot_id in nodes and nodes[node.snapshot_id] != node:
            raise SourceClosureError("source_conflict")
        nodes[node.snapshot_id] = node
    for root in root_snapshots:
        if root.snapshot_id in roots and roots[root.snapshot_id] != root:
            raise SourceClosureError("source_conflict")
        roots[root.snapshot_id] = root
    if len(selected_snapshot_ids) != len(set(selected_snapshot_ids)):
        raise SourceClosureError("source_conflict")
    chosen: list[StageSnapshot] = []
    for snapshot_id in selected_snapshot_ids:
        selected_node = nodes.get(snapshot_id)
        if selected_node is None:
            raise SourceClosureError("source_unknown")
        chosen.append(selected_node)
    if len(chosen) != len({node.key for node in chosen}):
        raise SourceClosureError("source_conflict")
    if {node.key for node in chosen} != required_stages:
        raise SourceClosureError("source_unknown")

    stages_by_key: dict[StageKey, StageSnapshot] = {}
    roots_by_key: dict[RootKey, RootSnapshot] = {}
    visiting: set[str] = set()
    visited: set[str] = set()
    ui_batch: str | None = None

    def visit_root(snapshot_id: str) -> None:
        root = roots.get(snapshot_id)
        if root is None or not all(
            (root.snapshot_id, root.resource_kind, root.resource_id, root.content_hash)
        ):
            raise SourceClosureError("source_unknown")
        previous = roots_by_key.get(root.key)
        if previous is not None and previous != root:
            raise SourceClosureError("source_conflict")
        current = current_root_hashes.get(root.key)
        if not current:
            raise SourceClosureError("source_unknown")
        if current != root.content_hash:
            raise SourceClosureError("source_stale")
        roots_by_key[root.key] = root

    def visit(snapshot_id: str) -> None:
        nonlocal ui_batch
        if snapshot_id in visiting:
            raise SourceClosureError("source_conflict")
        if snapshot_id in visited:
            return
        node = nodes.get(snapshot_id)
        if node is None:
            raise SourceClosureError("source_unknown")
        if not all(
            (
                node.requirement_id,
                node.chain_kind,
                node.stage,
                node.candidate_id,
                node.snapshot_id,
                node.content_hash,
                node.basis_hash,
            )
        ):
            raise SourceClosureError("source_unknown")
        if node.requirement_id != requirement_id:
            raise SourceClosureError("source_conflict")
        try:
            valid_stage = node.stage in stage_names(node.chain_kind)
        except KeyError:
            valid_stage = False
        if not valid_stage:
            raise SourceClosureError("source_conflict")
        if node.disposition != "available":
            raise SourceClosureError("source_stale")
        previous = stages_by_key.get(node.key)
        if previous is not None and previous.snapshot_id != node.snapshot_id:
            raise SourceClosureError("source_conflict")
        stages_by_key[node.key] = node
        if node.chain_kind == "ui":
            if not node.source_batch_id:
                raise SourceClosureError("source_unknown")
            if ui_batch is not None and ui_batch != node.source_batch_id:
                raise SourceClosureError("source_conflict")
            ui_batch = node.source_batch_id
        if len(set(node.parent_snapshot_ids)) != len(node.parent_snapshot_ids):
            raise SourceClosureError("source_conflict")
        visiting.add(snapshot_id)
        parents: list[StageSnapshot] = []
        for parent_id in node.parent_snapshot_ids:
            visit(parent_id)
            parents.append(nodes[parent_id])
        actual_parents = {parent.key for parent in parents}
        expected_parents = {
            (kind_for_stage(name), name) for name in upstream_stages(node.chain_kind, node.stage)
        }
        if len(parents) != len(actual_parents) or actual_parents - expected_parents:
            raise SourceClosureError("source_conflict")
        if actual_parents != expected_parents:
            raise SourceClosureError("source_unknown")
        if not parents and not node.root_snapshot_ids:
            raise SourceClosureError("source_unknown")
        for root_id in node.root_snapshot_ids:
            visit_root(root_id)
        visiting.remove(snapshot_id)
        visited.add(snapshot_id)

    for selected in selected_snapshot_ids:
        visit(selected)
    for root_id in selected_root_ids:
        visit_root(root_id)
    if not roots_by_key:
        raise SourceClosureError("source_unknown")
    ordered_stages = tuple(stages_by_key[key] for key in sorted(stages_by_key))
    ordered_roots = tuple(roots_by_key[key] for key in sorted(roots_by_key))
    semantic = {
        "stages": [
            {
                "requirementId": node.requirement_id,
                "chainKind": node.chain_kind,
                "stage": node.stage,
                "candidateId": node.candidate_id,
                "snapshotId": node.snapshot_id,
                "contentHash": node.content_hash,
                "basisHash": node.basis_hash,
                "parentSnapshotIds": sorted(node.parent_snapshot_ids),
                "rootSnapshotIds": sorted(node.root_snapshot_ids),
                "sourceBatchId": node.source_batch_id,
            }
            for node in ordered_stages
        ],
        "roots": [
            {
                "snapshotId": root.snapshot_id,
                "resourceKind": root.resource_kind,
                "resourceId": root.resource_id,
                "contentHash": root.content_hash,
                "sourceBatchId": root.source_batch_id,
            }
            for root in ordered_roots
        ],
    }
    payload = json.dumps(semantic, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return SourceClosure(
        f"sha256:{sha256(payload.encode('utf-8')).hexdigest()}", ordered_stages, ordered_roots
    )
