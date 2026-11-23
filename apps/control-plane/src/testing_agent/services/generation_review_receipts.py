"""Reserve idempotent candidate review receipts within the caller transaction."""

# transaction-bound: the reservation and review action commit or roll back together.

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.models.generation_candidates import AiGenerationReviewReceipt


async def reserve_content_receipt(
    session: AsyncSession,
    *,
    request_id: str,
    fingerprint: str,
    stage_id: str,
    candidate_id: str | None,
    attempt_id: str | None,
    decision: str,
    actor_id: str,
    comment: str,
) -> tuple[AiGenerationReviewReceipt, bool]:
    """Reserve or read a completed matching receipt; the caller owns transactions."""
    query = (
        select(AiGenerationReviewReceipt)
        .where(AiGenerationReviewReceipt.request_id == request_id)
        .execution_options(populate_existing=True)
    )
    receipt = await session.scalar(query)
    if receipt is None:
        reserved = AiGenerationReviewReceipt(
            receipt_id=uuid4().hex,
            request_id=request_id,
            request_fingerprint=fingerprint,
            stage_id=stage_id,
            candidate_id=candidate_id,
            attempt_id=attempt_id,
            decision=decision,
            actor_id=actor_id,
            comment=comment,
        )
        try:
            async with session.begin_nested():
                session.add(reserved)
                await session.flush()
            return reserved, False
        except IntegrityError:
            pass
        except OperationalError as exc:
            if (getattr(exc.orig, "args", ()) or (None,))[0] in {1205, 1213, 3572}:
                raise dynamic_error(ErrBadRequest, "操作正在处理中，请稍后重试") from exc
            raise
    receipt = await session.scalar(query.with_for_update())
    if receipt is None:
        raise dynamic_error(ErrBadRequest, "操作正在处理中，请稍后重试")
    if (
        receipt.request_fingerprint != fingerprint
        or receipt.actor_id != actor_id
        or receipt.stage_id != stage_id
        or receipt.candidate_id != candidate_id
        or receipt.attempt_id != attempt_id
        or receipt.decision != decision
        or not receipt.result_content_token
    ):
        raise dynamic_error(ErrBadRequest, "请求标识已用于其他审核操作")
    return receipt, True
