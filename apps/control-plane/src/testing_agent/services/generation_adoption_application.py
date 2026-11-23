"""Authorized application boundary for adopting one generation candidate."""

from dataclasses import replace
from uuid import uuid5

from testing_agent.core.errors import AppError, ErrBadRequest, dynamic_error
from testing_agent.domain.generation_chain import stage_names, upstream_stages
from testing_agent.domain.generation_root_fingerprints import IncompleteRootInput
from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.schemas.generation_candidates import (
    AdoptionCheck,
    CandidateAdoptRequest,
    CandidateRunRequest,
    CurrentClearRequest,
    SourceSelection,
)
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_adoption_roots import lock_adoption_roots
from testing_agent.services.generation_application_scope import GenerationApplicationScope
from testing_agent.services.generation_candidate_adoption import inspect_candidate_adoption
from testing_agent.services.generation_candidate_adoption_receipt import (
    CandidateAdoptionReceipt,
    adopt_candidate_once,
    replay_candidate_adoption,
)
from testing_agent.services.generation_chain import GenerationChainService
from testing_agent.services.generation_current_clear import (
    ClearedCurrentReceipt,
    clear_current_once,
)
from testing_agent.services.generation_document_preparation import (
    PreparedRequirementDocument,
    prepare_requirement_document,
)
from testing_agent.services.generation_source_errors import closure_error, source_error


class CandidateAdoptionApplication:
    """Own review authorization, source preparation and the adoption transaction.

    This boundary owns commit/rollback and must receive a fresh request-scoped
    session with no unrelated pending changes.
    """

    def __init__(self, chain: GenerationChainService) -> None:
        self.chain = chain
        self.session = chain.tasks.session
        self.scope = GenerationApplicationScope(chain, action="review")

    async def _prepare_document(
        self, requirement_id: str, kind: DesignKind
    ) -> PreparedRequirementDocument | None:
        await self.session.rollback()
        if kind not in {"requirement_analysis", "function"}:
            return None
        if self.chain.files is None:
            raise dynamic_error(ErrBadRequest, "需求文件存储不可用")
        prepared = await prepare_requirement_document(
            self.session, requirement_id=requirement_id, files=self.chain.files
        )
        await self.session.rollback()
        return prepared

    async def preview(
        self,
        *,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        request: CandidateAdoptRequest,
        actor_id: str,
    ) -> AdoptionCheck:
        """Explain all current upstream blocks without freezing or adopting."""
        try:
            self.chain.validate_stage(kind, stage)
            parent = await self.scope.authorize(requirement_id, actor_id)
            prepared = await self._prepare_document(requirement_id, kind)
            await self.scope.lock_parents(requirement_id, actor_id, parent)
            roots = await lock_adoption_roots(
                self.session,
                requirement_id=requirement_id,
                kind=kind,
                stage=stage,
                request=request,
                prepared_document=prepared,
            )
            verified = await inspect_candidate_adoption(
                self.session,
                requirement_id=requirement_id,
                kind=kind,
                stage=stage,
                request=request,
                current_root_hashes=roots,
            )
            await self.session.rollback()
            return verified.check
        except IncompleteRootInput as exc:
            await self.session.rollback()
            raise source_error("source_unknown") from exc
        except SourceClosureError as exc:
            await self.session.rollback()
            raise closure_error(exc) from exc
        except Exception:
            await self.session.rollback()
            raise

    async def clear(
        self,
        *,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        request: CurrentClearRequest,
        actor_id: str,
    ) -> ClearedCurrentReceipt:
        """Clear one current slot; retain candidates and replay the original receipt."""
        try:
            self.chain.validate_stage(kind, stage)
            parent = await self.scope.authorize(requirement_id, actor_id)
            await self.session.rollback()
            await self.scope.lock_parents(requirement_id, actor_id, parent)
            result = await clear_current_once(
                self.session,
                requirement_id=requirement_id,
                kind=kind,
                stage=stage,
                request=request,
                actor_id=actor_id,
            )
            await self.session.commit()
            return result
        except SourceClosureError as exc:
            await self.session.rollback()
            raise closure_error(exc) from exc
        except Exception:
            await self.session.rollback()
            raise

    async def adopt(
        self,
        *,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        request: CandidateAdoptRequest,
        actor_id: str,
    ) -> CandidateAdoptionReceipt:
        try:
            self.chain.validate_stage(kind, stage)
            parent = await self.scope.authorize(requirement_id, actor_id)
            # Replays still require current authorization, but do not need a
            # now-unavailable source file and never restore old current content.
            await self.session.rollback()
            await self.scope.lock_parents(requirement_id, actor_id, parent)
            replay = await replay_candidate_adoption(
                self.session,
                requirement_id=requirement_id,
                kind=kind,
                stage=stage,
                request=request,
                actor_id=actor_id,
            )
            if replay is not None:
                await self.session.rollback()
                return await self._continue(requirement_id, kind, stage, request, actor_id, replay)
            # Never hold business locks while reading the object store. After
            # preparation, reauthorize and recheck all parents and document IDs.
            prepared = await self._prepare_document(requirement_id, kind)
            await self.scope.lock_parents(requirement_id, actor_id, parent)
            # A concurrent retry may have committed while the document was read.
            replay = await replay_candidate_adoption(
                self.session,
                requirement_id=requirement_id,
                kind=kind,
                stage=stage,
                request=request,
                actor_id=actor_id,
            )
            if replay is not None:
                await self.session.rollback()
                return await self._continue(requirement_id, kind, stage, request, actor_id, replay)
            roots = await lock_adoption_roots(
                self.session,
                requirement_id=requirement_id,
                kind=kind,
                stage=stage,
                request=request,
                prepared_document=prepared,
            )
            result = await adopt_candidate_once(
                self.session,
                requirement_id=requirement_id,
                kind=kind,
                stage=stage,
                request=request,
                actor_id=actor_id,
                current_root_hashes=roots,
            )
            await self.session.commit()
            return await self._continue(requirement_id, kind, stage, request, actor_id, result)
        except IncompleteRootInput as exc:
            await self.session.rollback()
            raise source_error("source_unknown") from exc
        except SourceClosureError as exc:
            await self.session.rollback()
            raise closure_error(exc) from exc
        except Exception:
            await self.session.rollback()
            raise

    async def _continue(
        self,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        request: CandidateAdoptRequest,
        actor_id: str,
        receipt: CandidateAdoptionReceipt,
    ) -> CandidateAdoptionReceipt:
        """Dispatch separately, guarded by the token from this adoption receipt."""
        if not request.continue_after:
            return receipt
        stages = stage_names(kind)
        index = stages.index(stage)
        advisory_review = kind == "requirement_analysis" and stage == "requirement_review"
        if index + 1 >= len(stages) or (
            stage not in upstream_stages(kind, stages[index + 1]) and not advisory_review
        ):
            return replace(receipt, continuation_error="当前阶段没有可继续的依赖阶段")
        if not request.connection_id:
            return replace(receipt, continuation_error="请选择模型连接")
        from testing_agent.services.generation_dispatch_application import (
            CandidateDispatchApplication,
        )

        try:
            result = await CandidateDispatchApplication(self.chain).run(
                requirement_id=requirement_id,
                kind=kind,
                stage=stages[index + 1],
                request=CandidateRunRequest(
                    connection_id=request.connection_id,
                    instruction=request.instruction,
                    gitlab_connection_id=request.gitlab_connection_id,
                    request_id=uuid5(request.request_id, "continue"),
                    required_current_source=SourceSelection(
                        chain_kind=kind,
                        stage=stage,
                        source_kind="current",
                        expected_current_token=receipt.content_token,
                    ),
                ),
                actor_id=actor_id,
            )
        except AppError as exc:
            await self.session.rollback()
            return replace(receipt, continuation_error=exc.message)
        return replace(receipt, continuation_attempt_id=result.attempt_id)
