"""Guard preview and commit against source, target, actor and time changes."""

# transaction-bound: source and target locks must survive until the caller commits.

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.generation_import_preview import (
    issue_import_preview_token,
    validate_import_preview_token,
)
from testing_agent.domain.generation_import_source import CurrentImportSource
from testing_agent.domain.generation_source_closure import RootKey, SourceClosureError
from testing_agent.repositories.generation_import_targets import (
    ImportTargetState,
    lock_import_target_state,
)
from testing_agent.schemas.generation_candidates import CurrentImportRequest
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_current_import_source import lock_current_import_source
from testing_agent.services.generation_import_preview import import_preview_binding


@dataclass(frozen=True)
class VerifiedImportPreview:
    source: CurrentImportSource
    target: ImportTargetState
    preview_token: str
    expires_at: int


async def prepare_import_preview(
    session: AsyncSession,
    *,
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    current_token: str,
    target_id: str,
    actor_id: str,
    current_root_hashes: dict[RootKey, str],
    secret: str,
    now: int | None = None,
) -> VerifiedImportPreview:
    """Lock and bind a current source and target for a short-lived preview.

    The caller must authorize the actor, acquire project/sprint/requirement and
    root locks first, and end this transaction promptly. The target is locked
    before candidate sources, matching source-case lock ordering. This method
    does not itself calculate conflicts or write formal assets.
    """
    if target_id != target_id.strip():
        raise SourceClosureError("source_conflict")
    target = await lock_import_target_state(
        session, requirement_id=requirement_id, kind=kind, target_id=target_id
    )
    source = await lock_current_import_source(
        session,
        requirement_id=requirement_id,
        kind=kind,
        stage=stage,
        expected_current_token=current_token,
        current_root_hashes=current_root_hashes,
    )
    binding = import_preview_binding(actor_id=actor_id, source=source, target=target)
    token = issue_import_preview_token(binding, secret=secret, now=now)
    return VerifiedImportPreview(source, target, token, int(token.split(".")[1]))


async def verify_import_preview(
    session: AsyncSession,
    *,
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    request: CurrentImportRequest,
    actor_id: str,
    current_root_hashes: dict[RootKey, str],
    secret: str,
    now: int | None = None,
) -> tuple[CurrentImportSource, ImportTargetState]:
    """Recheck a preview inside the transaction that will write formal assets.

    The caller must reauthorize, calculate locked root fingerprints and retain
    all returned locks through the import and receipt commit. Successful request
    replay is handled by the receipt layer before invoking this function.
    """
    if request.target_id != request.target_id.strip():
        raise SourceClosureError("source_conflict")
    target = await lock_import_target_state(
        session, requirement_id=requirement_id, kind=kind, target_id=request.target_id
    )
    source = await lock_current_import_source(
        session,
        requirement_id=requirement_id,
        kind=kind,
        stage=stage,
        expected_current_token=request.expected_current_token,
        expected_lineage_hash=request.expected_lineage_hash,
        current_root_hashes=current_root_hashes,
    )
    binding = import_preview_binding(actor_id=actor_id, source=source, target=target)
    if not validate_import_preview_token(request.preview_token, binding, secret=secret, now=now):
        raise SourceClosureError("concurrent_change")
    return source, target
