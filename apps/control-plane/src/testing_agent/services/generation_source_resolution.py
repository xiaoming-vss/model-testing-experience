"""Load and lock only candidate records reachable from selected sources."""

# transaction-bound: discover, lock and verify source snapshots in one transaction.

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.ai_tasks import task_type_for
from testing_agent.domain.generation_chain import stage_names
from testing_agent.domain.generation_root_fingerprints import (
    IncompleteRootInput,
    fingerprint_generation_basis,
)
from testing_agent.domain.generation_source_closure import (
    RootKey,
    RootSnapshot,
    SourceClosure,
    SourceClosureError,
    StageKey,
)
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    RequirementGenerationChain,
)
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.repositories.generation_root_inputs import lock_revision_attachment_hashes
from testing_agent.repositories.requirement_design import requirement_scope
from testing_agent.schemas.generation_candidates import FrozenCandidateInput
from testing_agent.services.generation_source_reconstruction import (
    StoredCandidateSource,
    reconstruct_source_closure,
)


@dataclass(frozen=True)
class ResolvedCandidateSelection:
    """An authorized server-resolved selection, including current-slot checks."""

    chain_kind: str
    stage: str
    candidate_id: str
    snapshot_id: str
    candidate_token: str


@dataclass(frozen=True)
class _ReadCandidate:
    record: StoredCandidateSource
    chain_id: str
    stage_id: str
    candidate_token: str
    current_attempt_id: str | None
    derived_from_candidate_id: str | None
    source_snapshot: dict[str, Any] | None
    context: dict[str, Any] | None


def _project(
    candidate: AiGenerationCandidate, chain: RequirementGenerationChain, stage: AiGenerationStage
) -> _ReadCandidate:
    snapshot = candidate.source_snapshot_json
    source = snapshot.get("source") if isinstance(snapshot, dict) else None
    batch = source.get("uiSourceBatchId") if isinstance(source, dict) else None
    return _ReadCandidate(
        record=StoredCandidateSource(
            requirement_id=chain.requirement_id,
            chain_kind=chain.kind,
            stage=stage.stage,
            candidate_id=candidate.candidate_id,
            snapshot_id=candidate.snapshot_id,
            content=candidate.content,
            format=candidate.format,
            content_hash=candidate.content_hash,
            basis_hash=candidate.basis_hash,
            lineage_hash=candidate.lineage_hash,
            disposition=candidate.disposition,
            source_batch_id=str(batch) if batch else None,
            source_manifest=deepcopy(candidate.source_manifest_json),
        ),
        chain_id=candidate.chain_id,
        stage_id=candidate.stage_id,
        candidate_token=candidate.candidate_token,
        current_attempt_id=candidate.current_attempt_id,
        derived_from_candidate_id=candidate.derived_from_candidate_id,
        source_snapshot=deepcopy(candidate.source_snapshot_json),
        context=deepcopy(candidate.context_json),
    )


async def read_closure_candidates(
    session: AsyncSession, closure: SourceClosure
) -> dict[str, AiGenerationCandidate]:
    """Return the already locked candidate rows for a verified closure."""
    candidate_ids = tuple(sorted({node.candidate_id for node in closure.stages}))
    if not candidate_ids:
        return {}
    rows = (
        await session.scalars(
            select(AiGenerationCandidate)
            .where(AiGenerationCandidate.candidate_id.in_(candidate_ids))
            .execution_options(populate_existing=True)
        )
    ).all()
    candidates = {row.candidate_id: row for row in rows}
    if set(candidates) != set(candidate_ids):
        raise SourceClosureError("concurrent_change")
    return candidates


async def lock_candidate_source_closure(
    session: AsyncSession,
    *,
    requirement_id: str,
    selections: tuple[ResolvedCandidateSelection, ...],
    required_stages: frozenset[StageKey],
    current_root_hashes: dict[RootKey, str],
    direct_roots: tuple[RootSnapshot, ...] = (),
    freeze_sources: bool = True,
) -> SourceClosure:
    """Discover, lock and validate a source graph in the caller's transaction.

    Before calling, the service must authorize the requirement, resolve current
    selections against their current-slot tokens, lock parent business resources,
    and calculate root fingerprints from authoritative data. Revision attachment
    metadata is locked after candidate rows. The function does not commit. Any
    failure requires the caller to roll back. Read-only prechecks may set
    ``freeze_sources`` to false while keeping the locks until their transaction
    ends; they must never use that option to dispatch a new run.
    """
    selected_ids = [item.candidate_id for item in selections]
    if len(selected_ids) != len(set(selected_ids)):
        raise SourceClosureError("source_conflict")
    read: dict[str, _ReadCandidate] = {}
    pending = set(selected_ids)
    while pending:
        rows = (
            await session.execute(
                select(
                    AiGenerationCandidate,
                    RequirementGenerationChain,
                    AiGenerationStage,
                    AiGenerateTask,
                )
                .join(
                    RequirementGenerationChain,
                    AiGenerationCandidate.chain_id == RequirementGenerationChain.chain_id,
                )
                .join(AiGenerationStage, AiGenerationCandidate.stage_id == AiGenerationStage.id)
                .join(AiGenerateTask, RequirementGenerationChain.task_id == AiGenerateTask.task_id)
                .where(
                    AiGenerationCandidate.candidate_id.in_(pending),
                    RequirementGenerationChain.requirement_id == requirement_id,
                    AiGenerationStage.task_id == AiGenerateTask.task_id,
                    *requirement_scope(requirement_id),
                )
            )
        ).all()
        if {row[0].candidate_id for row in rows} != pending:
            raise SourceClosureError("source_unknown")
        next_ids: set[str] = set()
        for candidate, chain, stage, task in rows:
            try:
                valid_stage = stage.stage in stage_names(chain.kind)
            except KeyError:
                valid_stage = False
            if not valid_stage or task.task_type != task_type_for(chain.kind):
                raise SourceClosureError("source_conflict")
            value = _project(candidate, chain, stage)
            if not isinstance(value.record.source_manifest, dict):
                raise SourceClosureError("source_unknown")
            try:
                manifest = FrozenCandidateInput.model_validate(value.record.source_manifest)
            except ValidationError as exc:
                raise SourceClosureError("source_unknown") from exc
            read[candidate.candidate_id] = value
            next_ids.update(item.candidate_id for item in manifest.selected_sources)
            if isinstance(value.source_snapshot, dict) and (
                value.source_snapshot.get("candidateProtocol") == "single-current/2"
            ):
                revision_parent = value.source_snapshot.get("revisionParent")
                if (
                    not isinstance(revision_parent, dict)
                    or not isinstance(revision_parent.get("candidateId"), str)
                    or not revision_parent["candidateId"]
                ):
                    raise SourceClosureError("source_unknown")
                next_ids.add(revision_parent["candidateId"])
        pending = next_ids - read.keys()
    for selection in selections:
        item = read[selection.candidate_id]
        if (
            item.record.chain_kind != selection.chain_kind
            or item.record.stage != selection.stage
            or item.record.snapshot_id != selection.snapshot_id
            or item.candidate_token != selection.candidate_token
        ):
            raise SourceClosureError("concurrent_change")
    locked = (
        list(
            (
                await session.scalars(
                    select(AiGenerationCandidate)
                    .where(AiGenerationCandidate.candidate_id.in_(tuple(sorted(read))))
                    .order_by(AiGenerationCandidate.candidate_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        if read
        else []
    )
    if len(locked) != len(read):
        raise SourceClosureError("concurrent_change")
    for candidate in locked:
        original = read[candidate.candidate_id]
        if (
            candidate.chain_id != original.chain_id
            or candidate.stage_id != original.stage_id
            or candidate.snapshot_id != original.record.snapshot_id
            or candidate.candidate_token != original.candidate_token
            or candidate.current_attempt_id != original.current_attempt_id
            or candidate.derived_from_candidate_id != original.derived_from_candidate_id
            or candidate.disposition != original.record.disposition
            or candidate.content != original.record.content
            or candidate.format != original.record.format
            or candidate.content_hash != original.record.content_hash
            or candidate.basis_hash != original.record.basis_hash
            or candidate.lineage_hash != original.record.lineage_hash
            or candidate.source_manifest_json != original.record.source_manifest
            or candidate.source_snapshot_json != original.source_snapshot
            or candidate.context_json != original.context
        ):
            raise SourceClosureError("concurrent_change")
    attachment_ids: set[str] = set()
    revision_owners: dict[str, tuple[str, str, str, str]] = {}
    for item in read.values():
        snapshot = item.source_snapshot
        if not isinstance(snapshot, dict):
            raise SourceClosureError("source_unknown")
        config = snapshot.get("config")
        if not isinstance(config, dict):
            raise SourceClosureError("source_unknown")
        revision = snapshot.get("revisionInstruction") or config.get("revisionInstruction")
        if revision or snapshot.get("currentOutput"):
            attachments = config.get("revisionAttachments") or []
            if not isinstance(attachments, list):
                raise SourceClosureError("source_unknown")
            for attachment in attachments:
                if not isinstance(attachment, dict) or not isinstance(
                    attachment.get("fileId"), str
                ):
                    raise SourceClosureError("source_unknown")
                attachment_ids.add(attachment["fileId"])
                if snapshot.get("candidateProtocol") == "single-current/2":
                    owner = (
                        snapshot.get("revisionAttemptId"),
                        snapshot.get("revisionActorId"),
                        attachment.get("filename"),
                        attachment.get("contentType"),
                    )
                    if any(not isinstance(value, str) or not value for value in owner):
                        raise SourceClosureError("source_unknown")
                    expected = (str(owner[0]), str(owner[1]), str(owner[2]), str(owner[3]))
                    previous = revision_owners.get(attachment["fileId"])
                    if previous is not None and previous != expected:
                        raise SourceClosureError("source_conflict")
                    revision_owners[attachment["fileId"]] = expected
    project_id = await session.scalar(
        select(Sprint.project_id)
        .join(Requirement, Requirement.sprint_id == Sprint.sprint_id)
        .where(Requirement.requirement_id == requirement_id)
    )
    if not project_id:
        raise SourceClosureError("source_unknown")
    try:
        attachment_hashes = await lock_revision_attachment_hashes(
            session,
            project_id=project_id,
            file_ids=tuple(sorted(attachment_ids)),
            expected_ownership=revision_owners,
        )
    except IncompleteRootInput as exc:
        raise SourceClosureError("source_unknown") from exc
    verified_basis_hashes = {}
    for candidate_id, item in read.items():
        if not isinstance(item.source_snapshot, dict) or not item.record.lineage_hash:
            raise SourceClosureError("source_unknown")
        try:
            manifest = FrozenCandidateInput.model_validate(item.record.source_manifest)
            roots = tuple(
                RootSnapshot(
                    root.snapshot_id,
                    root.resource_kind,
                    root.resource_id,
                    root.content_hash,
                    root.source_batch_id,
                )
                for root in manifest.root_sources
            )
            verified_basis_hashes[candidate_id] = fingerprint_generation_basis(
                kind=item.record.chain_kind,
                stage=item.record.stage,
                input_snapshot=item.source_snapshot,
                roots=roots,
                lineage_hash=item.record.lineage_hash,
                attachment_hashes=attachment_hashes,
            )
        except (IncompleteRootInput, ValidationError) as exc:
            raise SourceClosureError("source_unknown") from exc
    checked_revision_parents: set[str] = set()
    active_revision_parents: set[str] = set()

    def validate_revision_parent(candidate_id: str) -> None:
        if candidate_id in active_revision_parents:
            raise SourceClosureError("source_conflict")
        if candidate_id in checked_revision_parents:
            return
        child = read[candidate_id]
        snapshot = child.source_snapshot
        if (
            not isinstance(snapshot, dict)
            or snapshot.get("candidateProtocol") != "single-current/2"
        ):
            checked_revision_parents.add(candidate_id)
            return
        parent_ref = snapshot.get("revisionParent")
        if not isinstance(parent_ref, dict):
            raise SourceClosureError("source_unknown")
        parent_id = parent_ref.get("candidateId")
        if not isinstance(parent_id, str) or parent_id not in read:
            raise SourceClosureError("source_unknown")
        parent = read[parent_id]
        if (
            parent.chain_id != child.chain_id
            or parent.stage_id != child.stage_id
            or parent.record.disposition != "available"
            or parent_ref.get("snapshotId") != parent.record.snapshot_id
            or parent_ref.get("candidateToken") != parent.candidate_token
            or parent_ref.get("attemptId") != parent.current_attempt_id
            or parent_ref.get("contentHash") != parent.record.content_hash
            or snapshot.get("currentOutput") != parent.record.content
        ):
            raise SourceClosureError("source_stale")
        try:
            child_manifest = FrozenCandidateInput.model_validate(child.record.source_manifest)
            parent_manifest = FrozenCandidateInput.model_validate(parent.record.source_manifest)
        except ValidationError as exc:
            raise SourceClosureError("source_unknown") from exc
        if child_manifest.model_dump(exclude={"generation_mode"}) != parent_manifest.model_dump(
            exclude={"generation_mode"}
        ):
            raise SourceClosureError("source_conflict")
        active_revision_parents.add(candidate_id)
        validate_revision_parent(parent_id)
        active_revision_parents.remove(candidate_id)
        reconstruct_source_closure(
            requirement_id=requirement_id,
            selected_candidate_ids=(parent_id,),
            required_stages=frozenset({(parent.record.chain_kind, parent.record.stage)}),
            stored_candidates={key: value.record for key, value in read.items()},
            current_root_hashes=current_root_hashes,
            verified_basis_hashes=verified_basis_hashes,
        )
        checked_revision_parents.add(candidate_id)

    for candidate_id in read:
        validate_revision_parent(candidate_id)
    closure = reconstruct_source_closure(
        requirement_id=requirement_id,
        selected_candidate_ids=tuple(selected_ids),
        required_stages=required_stages,
        stored_candidates={key: value.record for key, value in read.items()},
        current_root_hashes=current_root_hashes,
        verified_basis_hashes=verified_basis_hashes,
        direct_roots=direct_roots,
    )
    if freeze_sources:
        now = datetime.now(UTC)
        for candidate in locked:
            if candidate.frozen_at is None:
                candidate.frozen_at = now
        await session.flush()
    return closure
