"""Authorized candidate editing, derivation and disposition commands."""

# transaction-bound: candidate, stage and audit locks must share the write transaction.

import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError

from testing_agent.core.errors import ErrBadRequest, ErrNotFound, dynamic_error
from testing_agent.db.savepoint import ensure_outer_transaction
from testing_agent.domain.ai_tasks import task_type_for
from testing_agent.domain.generation_chain import artifact_is_json
from testing_agent.domain.generation_content_hash import generation_content_hash
from testing_agent.domain.request_identity import request_signature
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationReviewReceipt,
    AiGenerationStageContent,
)
from testing_agent.repositories.generation_candidate_creation import (
    CandidateProvenance,
    create_candidate_from_successful_attempt,
)
from testing_agent.repositories.generation_candidate_storage import (
    CandidateEditSnapshot,
    delete_candidate_if_unchanged,
    edit_unfrozen_candidate_if_unchanged,
    reject_candidate_if_unchanged,
)
from testing_agent.schemas.generation_candidates import (
    CandidateDeriveRequest,
    CandidateDeriveResult,
    CandidateDetailView,
    CandidateDispositionRequest,
    CandidateDispositionResult,
    CandidateEditRequest,
)
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_artifact_validation import validate_generation_artifact
from testing_agent.services.generation_candidate_queries import CandidateQueries
from testing_agent.services.generation_chain import GenerationChainService


class CandidateCommands:
    def __init__(self, chain: GenerationChainService) -> None:
        self.chain = chain
        self.session = chain.tasks.session

    async def _authorize_write(self, requirement_id: str, user_id: str) -> None:
        requirement = await self.chain.scope(requirement_id, user_id)
        sprint = await self.chain.tasks.get_sprint(requirement.sprint_id)
        if sprint is None:
            raise ErrNotFound()
        sprint_id, project_id = sprint.sprint_id, sprint.project_id
        # Close the read snapshot, then lock parents in the existing project ->
        # sprint -> requirement order and recheck the actor's write permission.
        await self.session.commit()
        await self.chain.access.ensure_project_access(user_id, project_id, action="write")
        await self.chain.access.ensure_sprint_access(user_id, sprint_id, action="write")
        locked = await self.chain.tasks.get_requirement_for_update(requirement_id)
        if locked is None or locked.sprint_id != sprint_id:
            raise ErrNotFound()

    async def _lock_task(self, stage_id: str, requirement_id: str, kind: DesignKind) -> None:
        task_id = await self.session.scalar(
            select(AiGenerationStage.task_id).where(AiGenerationStage.id == stage_id)
        )
        task = await self.chain.tasks.get_task_for_update(task_id) if task_id else None
        if (
            task is None
            or task.requirement_id != requirement_id
            or task.task_type != task_type_for(kind)
        ):
            raise ErrNotFound()
        await self.chain.access.validate_task_scope(task)

    async def _reserve_receipt(
        self,
        *,
        request_id: str,
        fingerprint: str,
        stage_id: str,
        candidate_id: str,
        actor_id: str,
        decision: str,
        comment: str,
    ) -> tuple[AiGenerationReviewReceipt, bool]:
        query = (
            select(AiGenerationReviewReceipt)
            .where(AiGenerationReviewReceipt.request_id == request_id)
            .execution_options(populate_existing=True)
        )
        receipt = await self.session.scalar(query)
        if receipt is None:
            reserved = AiGenerationReviewReceipt(
                receipt_id=uuid4().hex,
                request_id=request_id,
                request_fingerprint=fingerprint,
                stage_id=stage_id,
                candidate_id=candidate_id,
                decision=decision,
                actor_id=actor_id,
                comment=comment,
            )
            try:
                await self.session.run_sync(ensure_outer_transaction)
                async with self.session.begin_nested():
                    self.session.add(reserved)
                    await self.session.flush()
                return reserved, False
            except IntegrityError:
                pass
            except OperationalError as exc:
                if (getattr(exc.orig, "args", ()) or (None,))[0] in {1205, 1213, 3572}:
                    raise dynamic_error(ErrBadRequest, "操作正在处理中，请稍后重试") from exc
                raise
        receipt = await self.session.scalar(query.with_for_update())
        if receipt is None:
            raise dynamic_error(ErrBadRequest, "操作正在处理中，请稍后重试")
        if (
            receipt.request_fingerprint != fingerprint
            or receipt.actor_id != actor_id
            or receipt.stage_id != stage_id
            or receipt.candidate_id != candidate_id
            or receipt.decision != decision
            or (decision != "deleted" and not receipt.result_candidate_token)
        ):
            raise dynamic_error(ErrBadRequest, "请求标识已用于其他候选操作")
        return receipt, True

    async def _edit_attempt(
        self,
        *,
        stage_id: str,
        kind: DesignKind,
        stage: str,
        candidate: AiGenerationCandidate,
        content: str,
        user_id: str,
    ) -> tuple[AiGenerationAttempt, str]:
        """Validate and record an edit while the caller holds the stage lock."""
        if artifact_is_json(stage):
            try:
                generation_content_hash(content, "json")
            except ValueError as exc:
                raise dynamic_error(ErrBadRequest, "阶段产物必须是合法且字段不重复的 JSON") from exc
        if kind == "function" and stage == "case_names":
            try:
                edited = json.loads(content)
                if (
                    isinstance(edited, dict)
                    and edited.get("artifactType") == "traceable_test_points"
                ):
                    edited["reviewStatus"] = "self_review_only"
                    edited.pop("reviewIssues", None)
                    content = json.dumps(edited, ensure_ascii=False)
            except ValueError:
                pass
        content, output_format = await validate_generation_artifact(
            self.chain.tasks, kind, stage, content, candidate.source_snapshot_json or {}
        )
        content_hash = generation_content_hash(content, output_format)
        maximum = await self.session.scalar(
            select(AiGenerationAttempt.attempt_no)
            .where(AiGenerationAttempt.stage_id == stage_id)
            .order_by(AiGenerationAttempt.attempt_no.desc())
            .limit(1)
            .with_for_update()
        )
        now = datetime.now(UTC)
        context = deepcopy(candidate.context_json) if candidate.context_json is not None else None
        if context is not None:
            context.pop("moduleGeneration", None)
        attempt = AiGenerationAttempt(
            id=uuid4().hex,
            stage_id=stage_id,
            attempt_no=(maximum or 0) + 1,
            operation="edit",
            requested_by=user_id,
            input_snapshot_json=deepcopy(candidate.source_snapshot_json),
            output_content=content,
            output_format=output_format,
            output_context_json=context,
            status="success",
            invalidated_reason="",
            created_at=now,
            finished_at=now,
        )
        self.session.add(attempt)
        await self.session.flush()
        return attempt, content_hash

    async def edit(
        self,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        candidate_id: str,
        body: CandidateEditRequest,
        user_id: str,
    ) -> CandidateDetailView:
        await self._authorize_write(requirement_id, user_id)
        queries = CandidateQueries(self.chain)
        scope = await queries.scope(requirement_id, kind, stage, user_id)
        if scope is None:
            raise ErrNotFound()
        await self._lock_task(scope[1], requirement_id, kind)
        stage_row = await self.session.scalar(
            select(AiGenerationStage)
            .where(AiGenerationStage.id == scope[1])
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        candidate = await self.session.scalar(
            select(AiGenerationCandidate)
            .where(
                AiGenerationCandidate.candidate_id == candidate_id,
                AiGenerationCandidate.chain_id == scope[0],
                AiGenerationCandidate.stage_id == scope[1],
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if stage_row is None or candidate is None:
            raise ErrNotFound()
        if (
            candidate.candidate_token != body.expected_candidate_token
            or candidate.current_attempt_id != body.expected_attempt_id
            or candidate.disposition != "available"
        ):
            raise dynamic_error(ErrBadRequest, "候选已变化，请刷新后重试")
        slot = await self.session.scalar(
            select(AiGenerationStageContent)
            .where(
                AiGenerationStageContent.stage_id == scope[1],
                AiGenerationStageContent.chain_id == scope[0],
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if slot is None:
            raise dynamic_error(ErrBadRequest, "候选阶段尚未初始化")
        if candidate.frozen_at is not None or slot.source_candidate_id == candidate_id:
            raise dynamic_error(ErrBadRequest, "该候选已采用或被引用，请派生新候选后修改")
        attempt, content_hash = await self._edit_attempt(
            stage_id=scope[1],
            kind=kind,
            stage=stage,
            candidate=candidate,
            content=body.content,
            user_id=user_id,
        )
        assert attempt.output_content is not None and attempt.output_format is not None
        updated = await edit_unfrozen_candidate_if_unchanged(
            self.session,
            chain_id=scope[0],
            stage_id=scope[1],
            candidate_id=candidate_id,
            expected_candidate_token=body.expected_candidate_token,
            expected_attempt_id=body.expected_attempt_id,
            replacement=CandidateEditSnapshot(
                attempt.id,
                attempt.output_content,
                attempt.output_format,
                attempt.output_context_json,
                content_hash,
            ),
        )
        if updated is None:
            await self.session.rollback()
            raise dynamic_error(ErrBadRequest, "候选已变化，请刷新后重试")
        await self.session.commit()
        return await queries.detail(requirement_id, kind, stage, candidate_id, user_id)

    async def derive(
        self,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        candidate_id: str,
        body: CandidateDeriveRequest,
        user_id: str,
    ) -> CandidateDeriveResult:
        await self._authorize_write(requirement_id, user_id)
        scope = await CandidateQueries(self.chain).scope(requirement_id, kind, stage, user_id)
        if scope is None:
            raise ErrNotFound()
        await self._lock_task(scope[1], requirement_id, kind)
        fingerprint = request_signature(
            "generation-candidate-derive",
            {
                "requirementId": requirement_id,
                "kind": kind,
                "stage": stage,
                "candidateId": candidate_id,
                "expectedCandidateToken": body.expected_candidate_token,
                "expectedAttemptId": body.expected_attempt_id,
                "content": body.content,
                "actorId": user_id,
            },
        )
        receipt, replay = await self._reserve_receipt(
            request_id=str(body.request_id),
            fingerprint=fingerprint,
            stage_id=scope[1],
            candidate_id=candidate_id,
            actor_id=user_id,
            decision="derived",
            comment="",
        )
        if not replay:
            stage_row = await self.session.scalar(
                select(AiGenerationStage)
                .where(AiGenerationStage.id == scope[1])
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            parent = await self.session.scalar(
                select(AiGenerationCandidate)
                .where(
                    AiGenerationCandidate.candidate_id == candidate_id,
                    AiGenerationCandidate.chain_id == scope[0],
                    AiGenerationCandidate.stage_id == scope[1],
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if stage_row is None or parent is None:
                await self.session.rollback()
                raise ErrNotFound()
            if (
                parent.candidate_token != body.expected_candidate_token
                or parent.current_attempt_id != body.expected_attempt_id
            ):
                await self.session.rollback()
                raise dynamic_error(ErrBadRequest, "候选已变化，请刷新后重试")
            attempt, _ = await self._edit_attempt(
                stage_id=scope[1],
                kind=kind,
                stage=stage,
                candidate=parent,
                content=body.content,
                user_id=user_id,
            )
            if parent.generation_mode not in {"current", "trial"}:
                await self.session.rollback()
                raise dynamic_error(ErrBadRequest, "候选生成模式未知，无法派生")
            mode = cast(Literal["current", "trial"], parent.generation_mode)
            source_manifest = (
                deepcopy(parent.source_manifest_json)
                if isinstance(parent.source_manifest_json, dict)
                else None
            )
            derived = await create_candidate_from_successful_attempt(
                self.session,
                chain_id=scope[0],
                stage_id=scope[1],
                attempt_id=attempt.id,
                provenance=CandidateProvenance(
                    mode,
                    source_manifest,
                    (parent.lineage_hash or None) if source_manifest is not None else None,
                    parent.basis_hash or None,
                    parent.candidate_id,
                ),
            )
            receipt.result_candidate_id = derived.candidate_id
            receipt.result_snapshot_id = derived.snapshot_id
            receipt.result_candidate_token = derived.candidate_token
        if (
            not receipt.result_candidate_id
            or not receipt.result_snapshot_id
            or not receipt.result_candidate_token
        ):
            await self.session.rollback()
            raise dynamic_error(ErrBadRequest, "候选派生回执不完整，请刷新后重试")
        result = CandidateDeriveResult(
            request_id=body.request_id,
            candidate_id=receipt.result_candidate_id,
            snapshot_id=receipt.result_snapshot_id,
            candidate_token=receipt.result_candidate_token,
        )
        await self.session.commit()
        return result

    async def dispose(
        self,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        candidate_id: str,
        body: CandidateDispositionRequest,
        user_id: str,
    ) -> CandidateDispositionResult:
        await self._authorize_write(requirement_id, user_id)
        scope = await CandidateQueries(self.chain).scope(requirement_id, kind, stage, user_id)
        if scope is None:
            raise ErrNotFound()
        decision: Literal["rejected", "deleted"] = (
            "rejected" if body.action == "reject" else "deleted"
        )
        request_id = str(body.request_id)
        fingerprint = request_signature(
            "generation-candidate-disposition",
            {
                "requirementId": requirement_id,
                "kind": kind,
                "stage": stage,
                "candidateId": candidate_id,
                "expectedCandidateToken": body.expected_candidate_token,
                "action": body.action,
                "comment": body.comment,
                "actorId": user_id,
            },
        )
        receipt, replay = await self._reserve_receipt(
            request_id=request_id,
            fingerprint=fingerprint,
            stage_id=scope[1],
            candidate_id=candidate_id,
            actor_id=user_id,
            decision=decision,
            comment=body.comment,
        )
        if replay:
            token = receipt.result_candidate_token
        elif body.action == "reject":
            token = await reject_candidate_if_unchanged(
                self.session,
                chain_id=scope[0],
                stage_id=scope[1],
                candidate_id=candidate_id,
                expected_candidate_token=body.expected_candidate_token,
            )
            if not token:
                await self.session.rollback()
                raise dynamic_error(ErrBadRequest, "候选已变化或正在作为当前内容，请刷新后重试")
            receipt.result_candidate_token = token
        else:
            token = None
            if not await delete_candidate_if_unchanged(
                self.session,
                chain_id=scope[0],
                stage_id=scope[1],
                candidate_id=candidate_id,
                expected_candidate_token=body.expected_candidate_token,
            ):
                await self.session.rollback()
                raise dynamic_error(ErrBadRequest, "候选已变化或正在作为当前内容，请刷新后重试")
        await self.session.commit()
        return CandidateDispositionResult(
            request_id=body.request_id,
            candidate_id=candidate_id,
            disposition=decision,
            candidate_token=token,
        )
