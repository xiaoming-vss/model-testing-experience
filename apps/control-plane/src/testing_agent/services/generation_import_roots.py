"""Resolve current import roots from authorized, server-owned resources."""

# transaction-bound: business root locks stay held through source and target validation.

from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.generation_root_fingerprints import IncompleteRootInput
from testing_agent.domain.generation_source_closure import RootKey, SourceClosureError
from testing_agent.models.generation_candidates import AiGenerationStageContent
from testing_agent.repositories.generation_candidate_storage import candidate_stage_scope
from testing_agent.repositories.generation_root_inputs import (
    lock_api_interface_root,
    lock_ui_repository_cases_root,
)
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_document_preparation import (
    PreparedRequirementDocument,
    lock_prepared_requirement_root,
)


async def lock_import_roots(
    session: AsyncSession,
    *,
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    expected_current_token: str,
    prepared_document: PreparedRequirementDocument | None = None,
) -> dict[RootKey, str]:
    """Recompute roots from the bound task and persisted current UI source.

    The caller authorizes and locks the project, sprint, requirement and bound
    tasks first. Requirement objects must be prepared outside these locks. UI
    source is read from the persisted current slot, not from a request; source
    and token are rechecked by the import guard after the root locks are held.
    """
    scope = await candidate_stage_scope(
        session, requirement_id=requirement_id, kind=kind, stage=stage
    )
    if scope is None:
        raise SourceClosureError("source_unknown")
    chain_id, stage_id, task = scope
    try:
        if kind == "function":
            if prepared_document is None or prepared_document.requirement_id != requirement_id:
                raise SourceClosureError("source_unknown")
            root = await lock_prepared_requirement_root(session, prepared=prepared_document)
        elif kind == "api":
            root = await lock_api_interface_root(session, task=task)
        elif kind == "ui":
            row = (
                await session.execute(
                    select(
                        AiGenerationStageContent.content_token,
                        AiGenerationStageContent.source_snapshot_json,
                    ).where(
                        AiGenerationStageContent.chain_id == chain_id,
                        AiGenerationStageContent.stage_id == stage_id,
                        AiGenerationStageContent.source_candidate_id.is_not(None),
                    )
                )
            ).one_or_none()
            if row is None:
                raise SourceClosureError("pending_upstream")
            if row[0] != expected_current_token:
                raise SourceClosureError("concurrent_change")
            snapshot = row[1]
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
