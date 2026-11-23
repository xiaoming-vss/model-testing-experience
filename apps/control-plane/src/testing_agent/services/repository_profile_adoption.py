"""Authorized adoption of one repository profile candidate."""

# transaction-bound: profile, material, current slots and receipt commit together.

from typing import cast

from sqlalchemy import select

from testing_agent.core.errors import ErrBadRequest, ErrNotFound, dynamic_error
from testing_agent.domain.generation_content_hash import generation_content_hash
from testing_agent.domain.generation_root_fingerprints import IncompleteRootInput
from testing_agent.domain.generation_source_closure import RootSnapshot, SourceClosureError
from testing_agent.domain.repository_profile import parse_repository_profile
from testing_agent.domain.request_identity import request_signature
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationReviewReceipt,
)
from testing_agent.repositories.generation_candidate_storage import (
    candidate_stage_scope,
    replace_current_if_unchanged,
)
from testing_agent.schemas.generation_candidates import CandidateAdoptRequest
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_application_scope import GenerationApplicationScope
from testing_agent.services.generation_candidate_adoption_receipt import CandidateAdoptionReceipt
from testing_agent.services.generation_chain import GenerationChainService
from testing_agent.services.generation_document_preparation import (
    lock_prepared_requirement_root,
    prepare_requirement_document,
)
from testing_agent.services.generation_review_receipts import reserve_content_receipt
from testing_agent.services.generation_source_errors import closure_error, source_error
from testing_agent.services.repository_profile_candidates import (
    PROFILE_CANDIDATE_PROTOCOL,
    profile_candidate_basis,
)

PROFILE_KIND = cast(DesignKind, "repository_profile")
PROFILE_STAGE = "generate"


def _fingerprint(requirement_id: str, request: CandidateAdoptRequest, actor_id: str) -> str:
    return request_signature(
        "repository-profile-candidate-adopt",
        {
            "requirementId": requirement_id,
            "actorId": actor_id,
            "request": request.model_dump(mode="json", by_alias=True, exclude={"request_id"}),
        },
    )


class RepositoryProfileAdoption:
    """Validate actual material and atomically adopt one profile candidate."""

    def __init__(self, chain: GenerationChainService) -> None:
        self.chain = chain
        self.session = chain.tasks.session
        self.scope = GenerationApplicationScope(chain, action="review")

    async def _stage(self, requirement_id: str) -> tuple[str, str]:
        scope = await candidate_stage_scope(
            self.session, requirement_id=requirement_id, kind=PROFILE_KIND, stage=PROFILE_STAGE
        )
        if scope is None:
            raise ErrNotFound()
        return scope[0], scope[1]

    async def _replay(
        self, requirement_id: str, request: CandidateAdoptRequest, actor_id: str, stage_id: str
    ) -> CandidateAdoptionReceipt | None:
        receipt = await self.session.scalar(
            select(AiGenerationReviewReceipt)
            .where(AiGenerationReviewReceipt.request_id == str(request.request_id))
            .execution_options(populate_existing=True)
        )
        if receipt is None:
            return None
        if (
            receipt.request_fingerprint != _fingerprint(requirement_id, request, actor_id)
            or receipt.stage_id != stage_id
            or receipt.actor_id != actor_id
            or receipt.candidate_id != request.candidate_id
            or receipt.attempt_id != request.expected_attempt_id
            or receipt.decision != "profile_adopted"
            or not receipt.result_content_token
        ):
            raise dynamic_error(ErrBadRequest, "请求标识已用于其他审核操作")
        return CandidateAdoptionReceipt(
            str(request.request_id), request.candidate_id, receipt.result_content_token, True
        )

    @staticmethod
    def validate_candidate(
        candidate: AiGenerationCandidate, *, document_root: RootSnapshot
    ) -> None:
        snapshot = candidate.source_snapshot_json
        source = snapshot.get("source") if isinstance(snapshot, dict) else None
        recorded = source.get("requirementMaterialCurrent") if isinstance(source, dict) else None
        # Token changes alone do not invalidate the same adopted snapshot.
        keys = (
            "candidateId",
            "snapshotId",
            "taskId",
            "contentHash",
            "basisHash",
            "lineageHash",
            "documentRootHash",
        )
        requirement = source.get("requirement") if isinstance(source, dict) else None
        try:
            content_hash = generation_content_hash(candidate.content, candidate.format)
        except (TypeError, ValueError) as exc:
            raise SourceClosureError("source_unknown") from exc
        if (
            not isinstance(snapshot, dict)
            or snapshot.get("profileCandidateProtocol") != PROFILE_CANDIDATE_PROTOCOL
            or not isinstance(recorded, dict)
            or any(not isinstance(recorded.get(key), str) or not recorded[key] for key in keys)
            or not isinstance(requirement, dict)
            or not isinstance(requirement.get("documentContent"), str)
            or not requirement["documentContent"]
            or candidate.source_manifest_json
            != {"schemaVersion": PROFILE_CANDIDATE_PROTOCOL, "material": recorded}
            or candidate.basis_hash != profile_candidate_basis(snapshot)
            or candidate.lineage_hash != recorded["lineageHash"]
            or candidate.content_hash != content_hash
            or parse_repository_profile(candidate.content) is None
        ):
            raise SourceClosureError("source_unknown")
        if recorded["documentRootHash"] != document_root.content_hash:
            raise SourceClosureError("source_stale")

    async def adopt(
        self, *, requirement_id: str, request: CandidateAdoptRequest, actor_id: str
    ) -> CandidateAdoptionReceipt:
        if request.continue_after:
            raise ErrBadRequest()
        try:
            parent = await self.scope.authorize(requirement_id, actor_id)
            await self.session.rollback()
            await self.scope.lock_parents(requirement_id, actor_id, parent)
            _, stage_id = await self._stage(requirement_id)
            replay = await self._replay(requirement_id, request, actor_id, stage_id)
            if replay:
                await self.session.rollback()
                return replay
            await self.session.rollback()
            if self.chain.files is None:
                raise dynamic_error(ErrBadRequest, "需求文件存储不可用")
            document = await prepare_requirement_document(
                self.session, requirement_id=requirement_id, files=self.chain.files
            )
            await self.session.rollback()
            await self.scope.lock_parents(requirement_id, actor_id, parent)
            chain_id, stage_id = await self._stage(requirement_id)
            replay = await self._replay(requirement_id, request, actor_id, stage_id)
            if replay:
                await self.session.rollback()
                return replay
            root = await lock_prepared_requirement_root(self.session, prepared=document)
            candidate = await self.session.scalar(
                select(AiGenerationCandidate)
                .where(
                    AiGenerationCandidate.candidate_id == request.candidate_id,
                    AiGenerationCandidate.chain_id == chain_id,
                    AiGenerationCandidate.stage_id == stage_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if (
                candidate is None
                or candidate.candidate_token != request.expected_candidate_token
                or candidate.current_attempt_id != request.expected_attempt_id
                or candidate.disposition != "available"
            ):
                raise SourceClosureError("concurrent_change")
            self.validate_candidate(candidate, document_root=root)
            receipt, replayed = await reserve_content_receipt(
                self.session,
                request_id=str(request.request_id),
                fingerprint=_fingerprint(requirement_id, request, actor_id),
                stage_id=stage_id,
                candidate_id=request.candidate_id,
                attempt_id=request.expected_attempt_id,
                decision="profile_adopted",
                actor_id=actor_id,
                comment=request.comment,
            )
            if replayed:
                assert receipt.result_content_token
                result = CandidateAdoptionReceipt(
                    str(request.request_id),
                    request.candidate_id,
                    receipt.result_content_token,
                    True,
                )
            else:
                token = await replace_current_if_unchanged(
                    self.session,
                    stage_id=stage_id,
                    expected_content_token=request.expected_current_token,
                    candidate_id=request.candidate_id,
                    expected_candidate_token=request.expected_candidate_token,
                    actor_id=actor_id,
                    comment=request.comment,
                )
                if token is None:
                    raise SourceClosureError("concurrent_change")
                receipt.result_content_token = token
                receipt.result_candidate_id = request.candidate_id
                receipt.result_candidate_token = request.expected_candidate_token
                result = CandidateAdoptionReceipt(
                    str(request.request_id), request.candidate_id, token, False
                )
            await self.session.commit()
            return result
        except IncompleteRootInput as exc:
            await self.session.rollback()
            raise source_error("source_unknown") from exc
        except SourceClosureError as exc:
            await self.session.rollback()
            raise closure_error(exc) from exc
        except Exception:
            await self.session.rollback()
            raise
