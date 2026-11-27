"""Reconstruct source closures from trusted, locked candidate records.

The caller must authorize the requirement, lock every candidate and actual
business input, and independently compute the current root and candidate basis
fingerprints. This module never accepts a client-provided manifest as truth.
"""

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from testing_agent.domain.generation_chain import (
    kind_for_stage,
    optional_upstream_stages,
    upstream_stages,
)
from testing_agent.domain.generation_content_hash import generation_content_hash
from testing_agent.domain.generation_source_closure import (
    RootKey,
    RootSnapshot,
    SourceClosure,
    SourceClosureError,
    StageKey,
    StageSnapshot,
    resolve_source_closure,
)
from testing_agent.schemas.generation_candidates import FrozenCandidateInput


@dataclass(frozen=True)
class StoredCandidateSource:
    """One source record loaded from storage, not from the caller's request."""

    requirement_id: str
    chain_kind: str
    stage: str
    candidate_id: str
    snapshot_id: str
    content: str
    format: str
    content_hash: str | None
    basis_hash: str | None
    lineage_hash: str | None
    disposition: str
    source_batch_id: str | None
    source_manifest: dict[str, Any] | None


def reconstruct_source_closure(
    *,
    requirement_id: str,
    selected_candidate_ids: tuple[str, ...],
    required_stages: frozenset[StageKey],
    stored_candidates: dict[str, StoredCandidateSource],
    current_root_hashes: dict[RootKey, str],
    verified_basis_hashes: dict[str, str],
    direct_roots: tuple[RootSnapshot, ...] = (),
) -> SourceClosure:
    """Rebuild and validate stored manifests before a candidate can be reused.

    ``verified_basis_hashes`` must be produced by the caller from locked,
    authoritative inputs. A missing proof is unknown, never implicitly valid.
    """
    records: dict[str, StoredCandidateSource] = {}
    manifests: dict[str, FrozenCandidateInput] = {}
    nodes: dict[str, StageSnapshot] = {}
    roots: dict[str, RootSnapshot] = {}
    for root in direct_roots:
        previous = roots.get(root.snapshot_id)
        if previous is not None and previous != root:
            raise SourceClosureError("source_conflict")
        roots[root.snapshot_id] = root
    active: set[str] = set()
    visited: set[str] = set()
    descendants: dict[str, set[str]] = {}

    def visit(candidate_id: str) -> set[str]:
        if candidate_id in active:
            raise SourceClosureError("source_conflict")
        if candidate_id in visited:
            return descendants[candidate_id]
        record = stored_candidates.get(candidate_id)
        if record is None or record.candidate_id != candidate_id:
            raise SourceClosureError("source_unknown")
        if record.requirement_id != requirement_id:
            raise SourceClosureError("source_conflict")
        if record.disposition != "available":
            raise SourceClosureError("source_stale")
        if (
            not record.content_hash
            or not record.basis_hash
            or not record.lineage_hash
            or record.source_manifest is None
        ):
            raise SourceClosureError("source_unknown")
        try:
            actual_content_hash = generation_content_hash(record.content, record.format)
            manifest = FrozenCandidateInput.model_validate(record.source_manifest)
        except (ValueError, TypeError, ValidationError) as exc:
            raise SourceClosureError("source_unknown") from exc
        if (
            actual_content_hash != record.content_hash
            or manifest.lineage_hash != record.lineage_hash
        ):
            raise SourceClosureError("source_unknown")
        basis = verified_basis_hashes.get(candidate_id)
        if not basis:
            raise SourceClosureError("source_unknown")
        if basis != record.basis_hash:
            raise SourceClosureError("source_stale")
        records[candidate_id] = record
        manifests[candidate_id] = manifest
        active.add(candidate_id)
        ancestor_ids: set[str] = set()
        for selected in manifest.selected_sources:
            parent = stored_candidates.get(selected.candidate_id)
            if parent is None:
                raise SourceClosureError("source_unknown")
            if (
                parent.snapshot_id != selected.snapshot_id
                or parent.chain_kind != selected.chain_kind
                or parent.stage != selected.stage
            ):
                raise SourceClosureError("source_conflict")
            ancestor_ids.add(parent.candidate_id)
            ancestor_ids.update(visit(parent.candidate_id))
        for root in manifest.root_sources:
            value = RootSnapshot(
                root.snapshot_id,
                root.resource_kind,
                root.resource_id,
                root.content_hash,
                root.source_batch_id,
            )
            previous = roots.get(value.snapshot_id)
            if previous is not None and previous != value:
                raise SourceClosureError("source_conflict")
            roots[value.snapshot_id] = value
        parent_ids = tuple(selected.snapshot_id for selected in manifest.selected_sources)
        nodes[record.snapshot_id] = StageSnapshot(
            requirement_id=record.requirement_id,
            chain_kind=record.chain_kind,
            stage=record.stage,
            candidate_id=record.candidate_id,
            snapshot_id=record.snapshot_id,
            content_hash=record.content_hash,
            basis_hash=record.basis_hash,
            parent_snapshot_ids=parent_ids,
            root_snapshot_ids=tuple(root.snapshot_id for root in manifest.root_sources),
            source_batch_id=record.source_batch_id,
            disposition=record.disposition,
        )
        active.remove(candidate_id)
        visited.add(candidate_id)
        descendants[candidate_id] = ancestor_ids
        return ancestor_ids

    for selected_id in selected_candidate_ids:
        visit(selected_id)
    if len(nodes) != len(records):
        raise SourceClosureError("source_conflict")

    for candidate_id, record in records.items():
        manifest = manifests[candidate_id]
        expected_ids = descendants[candidate_id]
        declared = {source.candidate_id: source for source in manifest.sources}
        if (
            None in declared
            or set(declared) != expected_ids
            or len(declared) != len(manifest.sources)
        ):
            raise SourceClosureError("source_unknown")
        for ancestor_id in expected_ids:
            source = declared[ancestor_id]
            ancestor = records[ancestor_id]
            actual_node = nodes[ancestor.snapshot_id]
            if (
                source.requirement_id != ancestor.requirement_id
                or source.chain_kind != ancestor.chain_kind
                or source.stage != ancestor.stage
                or source.snapshot_id != ancestor.snapshot_id
                or source.content_hash != ancestor.content_hash
                or source.basis_hash != ancestor.basis_hash
                or source.source_batch_id != ancestor.source_batch_id
                or set(source.parent_snapshot_ids) != set(actual_node.parent_snapshot_ids)
                or set(source.root_snapshot_ids) != set(actual_node.root_snapshot_ids)
            ):
                raise SourceClosureError("source_conflict")
        parent_roots = {
            root.snapshot_id
            for ancestor_id in expected_ids
            for root in manifests[ancestor_id].root_sources
        }
        manifest_roots = {root.snapshot_id for root in manifest.root_sources}
        if not parent_roots.issubset(manifest_roots):
            raise SourceClosureError("source_unknown")
        required = frozenset(
            (kind_for_stage(name), name)
            for name in upstream_stages(record.chain_kind, record.stage)
        )
        optional = optional_upstream_stages(record.chain_kind, record.stage)
        required = required.union(
            (item.chain_kind, item.stage)
            for item in manifest.selected_sources
            if item.stage in optional and item.chain_kind == kind_for_stage(item.stage)
        )
        input_closure = resolve_source_closure(
            requirement_id=requirement_id,
            selected_snapshot_ids=tuple(item.snapshot_id for item in manifest.selected_sources),
            required_stages=required,
            stage_snapshots=tuple(nodes.values()),
            root_snapshots=tuple(roots.values()),
            current_root_hashes=current_root_hashes,
            selected_root_ids=tuple(manifest_roots),
        )
        if input_closure.lineage_hash != record.lineage_hash:
            raise SourceClosureError("source_conflict")

    return resolve_source_closure(
        requirement_id=requirement_id,
        selected_snapshot_ids=tuple(
            records[candidate_id].snapshot_id for candidate_id in selected_candidate_ids
        ),
        required_stages=required_stages,
        stage_snapshots=tuple(nodes.values()),
        root_snapshots=tuple(roots.values()),
        current_root_hashes=current_root_hashes,
        selected_root_ids=tuple(root.snapshot_id for root in direct_roots),
    )
