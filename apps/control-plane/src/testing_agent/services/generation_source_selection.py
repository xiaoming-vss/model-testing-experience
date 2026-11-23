"""Resolve current or explicitly selected candidate inputs for a new run.

This is an internal transaction primitive, not a generation endpoint. The caller
must authorize the requirement, lock its business resources and tasks in the
established order, and supply authoritative root fingerprints. On any failure
the caller must roll back the whole transaction, including frozen candidates.
"""

# transaction-bound: candidate graph and current slots must be locked together.

from dataclasses import dataclass
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.generation_chain import kind_for_stage, stage_names, upstream_stages
from testing_agent.domain.generation_source_closure import (
    RootKey,
    RootSnapshot,
    SourceClosureError,
    StageKey,
)
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
)
from testing_agent.repositories.generation_candidate_storage import (
    candidate_stage_scope,
    lock_stage_content,
)
from testing_agent.schemas.generation_candidates import (
    CandidateRunRequest,
    ChainKind,
    FrozenCandidateInput,
    FrozenCandidateSource,
    FrozenRootSource,
    FrozenSelectedSource,
    SourceSelection,
)
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_source_resolution import (
    ResolvedCandidateSelection,
    lock_candidate_source_closure,
    read_closure_candidates,
)


@dataclass(frozen=True)
class SelectedContent:
    chain_kind: str
    stage: str
    content: str
    format: str


@dataclass(frozen=True)
class ResolvedRunSources:
    manifest: FrozenCandidateInput
    selected_content: tuple[SelectedContent, ...]
    closure_content: tuple[SelectedContent, ...]


async def resolve_run_sources(
    session: AsyncSession,
    *,
    requirement_id: str,
    kind: str,
    stage: str,
    request: CandidateRunRequest,
    current_root_hashes: dict[RootKey, str],
    direct_roots: tuple[RootSnapshot, ...] = (),
) -> ResolvedRunSources:
    """Resolve exactly the stage dependencies, including all current ancestors."""
    try:
        if stage not in stage_names(kind):
            raise SourceClosureError("source_unknown")
    except KeyError as exc:
        raise SourceClosureError("source_unknown") from exc
    required: frozenset[StageKey] = frozenset(
        (kind_for_stage(name), name) for name in upstream_stages(kind, stage)
    )
    requested: dict[StageKey, SourceSelection] = {
        (item.chain_kind, item.stage): item for item in request.source_selections
    }
    required_current = request.required_current_source
    if required_current is not None:
        required_key: StageKey = (required_current.chain_kind, required_current.stage)
        advisory_review = (
            kind == "requirement_analysis"
            and stage == "extracting_text"
            and required_key == ("requirement_analysis", "requirement_review")
        )
        if request.generation_mode != "current" or (
            required_key not in required and not advisory_review
        ):
            raise SourceClosureError("source_conflict")
        if advisory_review:
            guard_scope = await candidate_stage_scope(
                session,
                requirement_id=requirement_id,
                kind="requirement_analysis",
                stage="requirement_review",
            )
            if guard_scope is None:
                raise SourceClosureError("concurrent_change")
            guard = (
                await session.execute(
                    select(
                        AiGenerationStageContent.content_token,
                        AiGenerationCandidate.candidate_id,
                        AiGenerationCandidate.snapshot_id,
                        AiGenerationCandidate.candidate_token,
                    )
                    .join(
                        AiGenerationCandidate,
                        AiGenerationCandidate.candidate_id
                        == AiGenerationStageContent.source_candidate_id,
                    )
                    .where(
                        AiGenerationStageContent.chain_id == guard_scope[0],
                        AiGenerationStageContent.stage_id == guard_scope[1],
                        AiGenerationCandidate.chain_id == guard_scope[0],
                        AiGenerationCandidate.stage_id == guard_scope[1],
                    )
                )
            ).one_or_none()
            if guard is None or guard[0] != required_current.expected_current_token:
                raise SourceClosureError("concurrent_change")
            await lock_candidate_source_closure(
                session,
                requirement_id=requirement_id,
                selections=(
                    ResolvedCandidateSelection(
                        "requirement_analysis", "requirement_review", guard[1], guard[2], guard[3]
                    ),
                ),
                required_stages=frozenset({required_key}),
                current_root_hashes=current_root_hashes,
                freeze_sources=False,
            )
            guard_slot = await lock_stage_content(
                session, chain_id=guard_scope[0], stage_id=guard_scope[1]
            )
            if (
                guard_slot is None
                or guard_slot.content_token != required_current.expected_current_token
                or guard_slot.source_candidate_id != guard[1]
                or guard_slot.invalidated_at is not None
            ):
                raise SourceClosureError("concurrent_change")
        else:
            requested[required_key] = required_current
    if request.generation_mode == "trial" and set(requested) != required:
        raise SourceClosureError("source_unknown")
    selected: list[ResolvedCandidateSelection] = []
    modes: dict[StageKey, Literal["current", "candidate"]] = {}
    current_checks: list[tuple[str, str, str, str]] = []
    for key in sorted(required):
        chain_kind, source_stage = key
        scope = await candidate_stage_scope(
            session,
            requirement_id=requirement_id,
            kind=cast(DesignKind, chain_kind),
            stage=source_stage,
        )
        if scope is None:
            raise SourceClosureError("pending_upstream")
        chain_id, stage_id, _ = scope
        choice = requested.get(key)
        mode: Literal["current", "candidate"] = choice.source_kind if choice else "current"
        modes[key] = mode
        if mode == "candidate":
            assert choice is not None
            assert choice.candidate_id and choice.snapshot_id and choice.expected_candidate_token
            selected.append(
                ResolvedCandidateSelection(
                    chain_kind,
                    source_stage,
                    choice.candidate_id,
                    choice.snapshot_id,
                    choice.expected_candidate_token,
                )
            )
            continue
        row = (
            await session.execute(
                select(
                    AiGenerationStageContent.content_token,
                    AiGenerationCandidate.candidate_id,
                    AiGenerationCandidate.snapshot_id,
                    AiGenerationCandidate.candidate_token,
                )
                .join(
                    AiGenerationCandidate,
                    AiGenerationCandidate.candidate_id
                    == AiGenerationStageContent.source_candidate_id,
                )
                .where(
                    AiGenerationStageContent.chain_id == chain_id,
                    AiGenerationStageContent.stage_id == stage_id,
                    AiGenerationCandidate.chain_id == chain_id,
                    AiGenerationCandidate.stage_id == stage_id,
                )
            )
        ).one_or_none()
        if row is None:
            raise SourceClosureError("pending_upstream")
        if choice and choice.expected_current_token != row[0]:
            raise SourceClosureError("concurrent_change")
        current_checks.append((chain_id, stage_id, row[0], row[1]))
        selected.append(
            ResolvedCandidateSelection(chain_kind, source_stage, row[1], row[2], row[3])
        )

    closure = await lock_candidate_source_closure(
        session,
        requirement_id=requirement_id,
        selections=tuple(selected),
        required_stages=required,
        current_root_hashes=current_root_hashes,
        direct_roots=direct_roots,
    )
    for check_chain_id, check_stage_id, expected_token, expected_candidate_id in current_checks:
        slot = await lock_stage_content(session, chain_id=check_chain_id, stage_id=check_stage_id)
        if (
            slot is None
            or slot.content_token != expected_token
            or slot.source_candidate_id != expected_candidate_id
        ):
            raise SourceClosureError("concurrent_change")
        if slot.invalidated_at is not None:
            raise SourceClosureError("source_stale")
    candidates = await read_closure_candidates(session, closure)

    selected_sources = [
        FrozenSelectedSource(
            chain_kind=cast(ChainKind, item.chain_kind),
            stage=item.stage,
            source_kind=modes[(item.chain_kind, item.stage)],
            candidate_id=item.candidate_id,
            snapshot_id=item.snapshot_id,
        )
        for item in selected
    ]
    manifest = FrozenCandidateInput(
        generation_mode=request.generation_mode,
        lineage_hash=closure.lineage_hash,
        sources=[
            FrozenCandidateSource(
                requirement_id=node.requirement_id,
                chain_kind=cast(ChainKind, node.chain_kind),
                stage=node.stage,
                source_kind=modes.get(node.key),
                candidate_id=node.candidate_id,
                snapshot_id=node.snapshot_id,
                content_hash=node.content_hash,
                basis_hash=node.basis_hash,
                source_batch_id=node.source_batch_id,
                parent_snapshot_ids=list(node.parent_snapshot_ids),
                root_snapshot_ids=list(node.root_snapshot_ids),
            )
            for node in closure.stages
        ],
        root_sources=[
            FrozenRootSource(
                snapshot_id=root.snapshot_id,
                resource_kind=root.resource_kind,
                resource_id=root.resource_id,
                content_hash=root.content_hash,
                source_batch_id=root.source_batch_id,
            )
            for root in closure.roots
        ],
        selected_sources=selected_sources,
    )
    return ResolvedRunSources(
        manifest=manifest,
        selected_content=tuple(
            SelectedContent(
                item.chain_kind,
                item.stage,
                candidates[item.candidate_id].content,
                candidates[item.candidate_id].format,
            )
            for item in selected
        ),
        closure_content=tuple(
            SelectedContent(
                node.chain_kind,
                node.stage,
                candidates[node.candidate_id].content,
                candidates[node.candidate_id].format,
            )
            for node in closure.stages
        ),
    )
