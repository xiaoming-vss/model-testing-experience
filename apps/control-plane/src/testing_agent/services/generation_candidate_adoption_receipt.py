"""Idempotent transaction wrapper for verified candidate adoption."""

# transaction-bound: reserve a receipt and adopt its candidate in one transaction.

from dataclasses import dataclass
from uuid import uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.db.savepoint import ensure_outer_transaction
from testing_agent.domain.generation_source_closure import RootKey, SourceClosureError
from testing_agent.domain.request_identity import request_signature
from testing_agent.models.generation_candidates import AiGenerationReviewReceipt
from testing_agent.repositories.generation_candidate_storage import candidate_stage_scope
from testing_agent.schemas.generation_candidates import CandidateAdoptRequest
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_candidate_adoption import adopt_verified_candidate
from testing_agent.services.generation_review_receipts import reserve_content_receipt


@dataclass(frozen=True)
class CandidateAdoptionReceipt:
    request_id: str
    candidate_id: str
    content_token: str
    replayed: bool
    continuation_attempt_id: str | None = None
    continuation_error: str = ""


def _adoption_fingerprint(
    requirement_id: str, kind: DesignKind, stage: str, request: CandidateAdoptRequest, actor_id: str
) -> str:
    body = request.model_dump(mode="json", by_alias=True, exclude={"request_id"})
    # Preserve fingerprints of completed requests from before continuation was
    # exposed, so an ordinary adoption can still be safely replayed.
    if request.connection_id is None:
        body.pop("connectionId", None)
    if request.instruction is None:
        body.pop("instruction", None)
    if not request.gitlab_connection_id:
        body.pop("gitlabConnectionId", None)
    return request_signature(
        "generation-candidate-adopt",
        {
            "requirementId": requirement_id,
            "kind": kind,
            "stage": stage,
            "actorId": actor_id,
            "request": body,
        },
    )


async def replay_candidate_adoption(
    session: AsyncSession,
    *,
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    request: CandidateAdoptRequest,
    actor_id: str,
) -> CandidateAdoptionReceipt | None:
    """Read a matching completed adoption without accessing external roots.

    Callers must authorize and lock the requirement and bound tasks first.
    The receipt cannot outlive its stage under the current storage schema.
    """
    if not actor_id:
        raise ErrBadRequest()
    scope = await candidate_stage_scope(
        session, requirement_id=requirement_id, kind=kind, stage=stage
    )
    if scope is None:
        raise SourceClosureError("source_unknown")
    receipt = await session.scalar(
        select(AiGenerationReviewReceipt)
        .where(AiGenerationReviewReceipt.request_id == str(request.request_id))
        .execution_options(populate_existing=True)
    )
    if receipt is None:
        return None
    if (
        receipt.request_fingerprint
        != _adoption_fingerprint(requirement_id, kind, stage, request, actor_id)
        or receipt.stage_id != scope[1]
        or receipt.actor_id != actor_id
        or receipt.candidate_id != request.candidate_id
        or receipt.attempt_id != request.expected_attempt_id
        or receipt.decision != "adopted"
        or not receipt.result_content_token
        or receipt.continuation_request_id
        != (str(uuid5(request.request_id, "continue")) if request.continue_after else None)
    ):
        raise dynamic_error(ErrBadRequest, "请求标识已用于其他审核操作")
    return CandidateAdoptionReceipt(
        str(request.request_id), request.candidate_id, receipt.result_content_token, True
    )


async def adopt_candidate_once(
    session: AsyncSession,
    *,
    requirement_id: str,
    kind: DesignKind,
    stage: str,
    request: CandidateAdoptRequest,
    actor_id: str,
    current_root_hashes: dict[RootKey, str],
) -> CandidateAdoptionReceipt:
    """Reserve a receipt and atomically adopt, without committing the caller.

    The caller must authorize and lock parent resources and tasks, calculate
    trusted current roots, and roll back the transaction on any failure. A
    committed replay returns its original token without modifying current state.
    A continuation is reserved here and dispatched after this transaction commits.
    """
    if not actor_id:
        raise ErrBadRequest()
    scope = await candidate_stage_scope(
        session, requirement_id=requirement_id, kind=kind, stage=stage
    )
    if scope is None:
        raise SourceClosureError("source_unknown")
    request_id = str(request.request_id)
    fingerprint = _adoption_fingerprint(requirement_id, kind, stage, request, actor_id)
    await session.run_sync(ensure_outer_transaction)
    async with session.begin_nested():
        receipt, replayed = await reserve_content_receipt(
            session,
            request_id=request_id,
            fingerprint=fingerprint,
            stage_id=scope[1],
            candidate_id=request.candidate_id,
            attempt_id=request.expected_attempt_id,
            decision="adopted",
            actor_id=actor_id,
            comment=request.comment,
        )
        if replayed:
            assert receipt.result_content_token
            return CandidateAdoptionReceipt(
                request_id,
                request.candidate_id,
                receipt.result_content_token,
                True,
            )
        token = await adopt_verified_candidate(
            session,
            requirement_id=requirement_id,
            kind=kind,
            stage=stage,
            request=request,
            actor_id=actor_id,
            current_root_hashes=current_root_hashes,
        )
        receipt.result_content_token = token
        receipt.result_candidate_id = request.candidate_id
        receipt.result_candidate_token = request.expected_candidate_token
        if request.continue_after:
            receipt.continuation_request_id = str(uuid5(request.request_id, "continue"))
        await session.flush()
        return CandidateAdoptionReceipt(request_id, request.candidate_id, token, False)
