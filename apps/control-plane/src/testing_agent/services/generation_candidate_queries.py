"""Authorized, requirement-scoped candidate reads for the new storage model."""

from dataclasses import asdict

from testing_agent.core.errors import ErrBadRequest, ErrNotFound, dynamic_error
from testing_agent.repositories.generation_candidate_storage import (
    candidate_stage_scope,
    current_source_candidate_id,
    get_stage_candidate,
    list_candidate_summaries,
    read_current_stage,
)
from testing_agent.repositories.generation_schema import candidate_schema_installed
from testing_agent.schemas.generation_candidates import (
    CandidateBasisSourceView,
    CandidateDetailView,
    CandidateListView,
    CandidateSourceTraceView,
    CandidateSummaryView,
    CurrentStageView,
)
from testing_agent.schemas.generation_chain import ChainSourceInputsView
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_chain import GenerationChainService
from testing_agent.services.ui_generation_sources import ui_source_inputs


def _ui_source(kind: str, snapshot: object) -> ChainSourceInputsView | None:
    if kind != "ui" or not isinstance(snapshot, dict):
        return None
    source = snapshot.get("source")
    projected = ui_source_inputs(source) if isinstance(source, dict) else None
    return ChainSourceInputsView.model_validate(projected) if projected else None


def _material_content(kind: str, stage: str, snapshot: object) -> str | None:
    """Expose only the frozen material used by the selected functional result."""
    if kind != "function" or stage not in {"requirement_analysis", "case_names"}:
        return None
    source = snapshot.get("source") if isinstance(snapshot, dict) else None
    content = source.get("sourceContent") if isinstance(source, dict) else None
    return content if isinstance(content, str) and content else None


def _source_trace(manifest: object) -> list[CandidateSourceTraceView]:
    """Return upstream stage selections without exposing the full source closure."""
    if not isinstance(manifest, dict):
        return []
    selected = manifest.get("selected_sources", manifest.get("selectedSources"))
    if not isinstance(selected, list):
        return []
    trace: list[CandidateSourceTraceView] = []
    for item in selected:
        if not isinstance(item, dict):
            continue
        try:
            trace.append(CandidateSourceTraceView.model_validate(item))
        except ValueError:
            continue
    return trace


def _basis_sources(manifest: object) -> list[CandidateBasisSourceView]:
    """Return the frozen stage snapshots this content was generated from."""
    if not isinstance(manifest, dict):
        return []
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        return []
    selected = manifest.get("selected_sources", manifest.get("selectedSources"))
    direct_keys = (
        {
            (item.get("chain_kind", item.get("chainKind")), item.get("stage"))
            for item in selected
            if isinstance(item, dict)
        }
        if isinstance(selected, list)
        else set()
    )
    basis: list[CandidateBasisSourceView] = []
    for item in sources:
        if not isinstance(item, dict):
            continue
        chain_kind = item.get("chain_kind", item.get("chainKind"))
        stage = item.get("stage")
        candidate_id = item.get("candidate_id", item.get("candidateId"))
        snapshot_id = item.get("snapshot_id", item.get("snapshotId"))
        if not all(
            isinstance(value, str) and value
            for value in (chain_kind, stage, candidate_id, snapshot_id)
        ):
            continue
        try:
            basis.append(
                CandidateBasisSourceView.model_validate(
                    {
                        "chain_kind": chain_kind,
                        "stage": stage,
                        "source_kind": item.get("source_kind", item.get("sourceKind")),
                        "candidate_id": candidate_id,
                        "snapshot_id": snapshot_id,
                        "direct": (chain_kind, stage) in direct_keys,
                    }
                )
            )
        except ValueError:
            continue
    return basis


class CandidateQueries:
    def __init__(self, chain: GenerationChainService) -> None:
        self.chain = chain
        self.session = chain.tasks.session

    async def scope(
        self, requirement_id: str, kind: DesignKind, stage: str, user_id: str
    ) -> tuple[str, str] | None:
        await self.chain.scope(requirement_id, user_id)
        self.chain.validate_stage(kind, stage)
        if not await candidate_schema_installed(self.session):
            raise dynamic_error(ErrBadRequest, "候选数据表尚未安装，请先完成数据库升级")
        row = await candidate_stage_scope(
            self.session, requirement_id=requirement_id, kind=kind, stage=stage
        )
        if row is None:
            return None
        await self.chain.access.validate_task_scope(row[2])
        return row[0], row[1]

    async def list(
        self,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        user_id: str,
        page: int,
        page_size: int,
    ) -> CandidateListView:
        scope = await self.scope(requirement_id, kind, stage, user_id)
        if scope is None:
            return CandidateListView(items=[], total=0, page=page, page_size=page_size)
        rows, total = await list_candidate_summaries(
            self.session, chain_id=scope[0], stage_id=scope[1], page=page, page_size=page_size
        )
        return CandidateListView(
            items=[CandidateSummaryView.model_validate(asdict(row)) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def detail(
        self, requirement_id: str, kind: DesignKind, stage: str, candidate_id: str, user_id: str
    ) -> CandidateDetailView:
        scope = await self.scope(requirement_id, kind, stage, user_id)
        if scope is None:
            raise ErrNotFound()
        candidate = await get_stage_candidate(
            self.session, chain_id=scope[0], stage_id=scope[1], candidate_id=candidate_id
        )
        if candidate is None:
            raise ErrNotFound()
        current_id = await current_source_candidate_id(
            self.session, chain_id=scope[0], stage_id=scope[1]
        )
        return CandidateDetailView.model_validate(
            {
                "candidate_id": candidate.candidate_id,
                "snapshot_id": candidate.snapshot_id,
                "candidate_token": candidate.candidate_token,
                "current_attempt_id": candidate.current_attempt_id,
                "derived_from_candidate_id": candidate.derived_from_candidate_id,
                "disposition": candidate.disposition,
                "generation_mode": candidate.generation_mode,
                "frozen_at": candidate.frozen_at,
                "created_by": candidate.created_by,
                "created_at": candidate.created_at,
                "is_current": candidate.candidate_id == current_id,
                "content": candidate.content,
                "format": candidate.format,
                "source_inputs": _ui_source(kind, candidate.source_snapshot_json),
                "material_content": _material_content(kind, stage, candidate.source_snapshot_json),
                "source_trace": _source_trace(candidate.source_manifest_json),
                "basis_sources": _basis_sources(candidate.source_manifest_json),
            }
        )

    async def current(
        self, requirement_id: str, kind: DesignKind, stage: str, user_id: str
    ) -> CurrentStageView:
        scope = await self.scope(requirement_id, kind, stage, user_id)
        if scope is None:
            raise ErrNotFound()
        row = await read_current_stage(self.session, chain_id=scope[0], stage_id=scope[1])
        if row is None:
            raise ErrNotFound()
        slot, active = row
        return CurrentStageView(
            stage=stage,
            current_token=slot.content_token,
            candidate_id=slot.source_candidate_id,
            source_attempt_id=slot.source_attempt_id,
            content=slot.content,
            format=slot.format,
            invalidated_at=slot.invalidated_at,
            invalidated_reason=slot.invalidated_reason,
            active=active,
            source_inputs=_ui_source(kind, slot.source_snapshot_json),
            material_content=_material_content(kind, stage, slot.source_snapshot_json),
            source_trace=_source_trace(slot.source_manifest_json),
            basis_sources=_basis_sources(slot.source_manifest_json),
        )
