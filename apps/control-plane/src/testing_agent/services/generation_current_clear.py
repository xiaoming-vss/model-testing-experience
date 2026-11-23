"""Clear one adopted stage without deleting candidates or execution evidence."""

# transaction-bound: the current token and idempotency receipt share one commit.

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest
from testing_agent.db.savepoint import ensure_outer_transaction
from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.domain.request_identity import request_signature
from testing_agent.models.generation_candidates import AiGenerationStageContent
from testing_agent.repositories.generation_candidate_storage import (
    candidate_stage_scope,
    clear_current_if_unchanged,
)
from testing_agent.schemas.generation_candidates import CurrentClearRequest
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_review_receipts import reserve_content_receipt


@dataclass(frozen=True)
class ClearedCurrentReceipt:
    request_id: str
    content_token: str
    replayed: bool


async def clear_current_once(
    session: AsyncSession,
    *,
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    request: CurrentClearRequest,
    actor_id: str,
) -> ClearedCurrentReceipt:
    """Clear with compare-and-swap; caller authorizes, locks parents and commits."""
    if not actor_id:
        raise ErrBadRequest()
    scope = await candidate_stage_scope(
        session, requirement_id=requirement_id, kind=kind, stage=stage
    )
    if scope is None:
        raise SourceClosureError("source_unknown")
    request_id = str(request.request_id)
    fingerprint = request_signature(
        "generation-current-clear",
        {
            "requirementId": requirement_id,
            "kind": kind,
            "stage": stage,
            "actorId": actor_id,
            "expectedCurrentToken": request.expected_current_token,
        },
    )
    await session.run_sync(ensure_outer_transaction)
    async with session.begin_nested():
        receipt, replayed = await reserve_content_receipt(
            session,
            request_id=request_id,
            fingerprint=fingerprint,
            stage_id=scope[1],
            candidate_id=None,
            attempt_id=None,
            decision="cleared",
            actor_id=actor_id,
            comment="",
        )
        if replayed:
            assert receipt.result_content_token
            return ClearedCurrentReceipt(request_id, receipt.result_content_token, True)
        slot = await session.scalar(
            select(AiGenerationStageContent)
            .where(AiGenerationStageContent.stage_id == scope[1])
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            slot is None
            or slot.chain_id != scope[0]
            or slot.stage != stage
            or slot.content_token != request.expected_current_token
        ):
            raise SourceClosureError("concurrent_change")
        token = await clear_current_if_unchanged(
            session, stage_id=scope[1], expected_content_token=request.expected_current_token
        )
        if token is None:
            raise SourceClosureError("concurrent_change")
        receipt.result_content_token = token
        await session.flush()
        return ClearedCurrentReceipt(request_id, token, False)
