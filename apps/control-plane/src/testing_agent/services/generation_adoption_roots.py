"""Recheck adoption roots using server-stored candidate and business data."""

# transaction-bound: root locks are held through candidate adoption.

from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.generation_root_fingerprints import IncompleteRootInput
from testing_agent.domain.generation_source_closure import RootKey, SourceClosureError
from testing_agent.models.generation_candidates import AiGenerationCandidate
from testing_agent.repositories.generation_candidate_storage import candidate_stage_scope
from testing_agent.repositories.generation_root_inputs import (
    lock_api_interface_root,
    lock_ui_repository_cases_root,
)
from testing_agent.schemas.generation_candidates import CandidateAdoptRequest
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_document_preparation import (
    PreparedRequirementDocument,
    lock_prepared_requirement_root,
)


async def lock_adoption_roots(
    session: AsyncSession,
    *,
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    request: CandidateAdoptRequest,
    prepared_document: PreparedRequirementDocument | None = None,
) -> dict[RootKey, str]:
    """Resolve roots from actual business resources and the selected candidate.

    Caller authorizes and locks all parent tasks before invoking. UI pin and
    selection are taken from the target candidate, not the current slot or the
    request; the candidate token and snapshot are rechecked by adoption.
    """
    scope = await candidate_stage_scope(
        session, requirement_id=requirement_id, kind=kind, stage=stage
    )
    if scope is None:
        raise SourceClosureError("source_unknown")
    chain_id, stage_id, task = scope
    try:
        if kind in {"requirement_analysis", "function"}:
            if prepared_document is None or prepared_document.requirement_id != requirement_id:
                raise SourceClosureError("source_unknown")
            root = await lock_prepared_requirement_root(session, prepared=prepared_document)
        elif kind == "api":
            root = await lock_api_interface_root(session, task=task)
        elif kind == "ui":
            row = (
                await session.execute(
                    select(
                        AiGenerationCandidate.candidate_token,
                        AiGenerationCandidate.current_attempt_id,
                        AiGenerationCandidate.source_snapshot_json,
                    ).where(
                        AiGenerationCandidate.chain_id == chain_id,
                        AiGenerationCandidate.stage_id == stage_id,
                        AiGenerationCandidate.candidate_id == request.candidate_id,
                    )
                )
            ).one_or_none()
            if row is None:
                raise SourceClosureError("source_unknown")
            if row[0] != request.expected_candidate_token or row[1] != request.expected_attempt_id:
                raise SourceClosureError("concurrent_change")
            snapshot = row[2]
            source = snapshot.get("source") if isinstance(snapshot, dict) else None
            if not isinstance(source, dict):
                raise SourceClosureError("source_unknown")
            root = await lock_ui_repository_cases_root(
                session, task=task, frozen_source=deepcopy(source)
            )
        else:
            raise SourceClosureError("source_unknown")
    except IncompleteRootInput as exc:
        raise SourceClosureError("source_unknown") from exc
    return {root.key: root.content_hash}
