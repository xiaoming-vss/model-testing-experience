"""Authorized application boundary for current-content import operations."""

# transaction-bound: project, requirement, roots, source and targets are checked together.

from typing import Any

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.generation_root_fingerprints import IncompleteRootInput
from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.schemas.generation_candidates import CurrentImportRequest
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_application_scope import (
    GenerationApplicationScope,
    GenerationParentIdentity,
)
from testing_agent.services.generation_chain import GenerationChainService
from testing_agent.services.generation_current_import import (
    CurrentImportCoordinator,
    CurrentImportPreview,
)
from testing_agent.services.generation_document_preparation import prepare_requirement_document
from testing_agent.services.generation_import_roots import lock_import_roots
from testing_agent.services.generation_source_errors import closure_error, source_error


class CurrentImportApplication:
    """Own authorization, two-phase source preparation and transaction boundaries."""

    def __init__(self, chain: GenerationChainService, *, secret: str) -> None:
        self.chain = chain
        self.session = chain.tasks.session
        self.coordinator = CurrentImportCoordinator(chain.imports, chain.api_importer)
        self.secret = secret
        self.scope = GenerationApplicationScope(chain, action="execute")

    async def _roots(
        self,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        current_token: str,
        actor_id: str,
        parent: GenerationParentIdentity,
    ) -> dict[tuple[str, str], str]:
        # Close the read transaction before any remote object read. The final
        # transaction reauthorizes and verifies all identities under row locks.
        await self.session.rollback()
        prepared = None
        if kind == "function":
            if self.chain.files is None:
                raise dynamic_error(ErrBadRequest, "需求文件存储不可用")
            prepared = await prepare_requirement_document(
                self.session, requirement_id=requirement_id, files=self.chain.files
            )
            await self.session.rollback()
        await self.scope.lock_parents(requirement_id, actor_id, parent)
        return await lock_import_roots(
            self.session,
            requirement_id=requirement_id,
            kind=kind,
            stage=stage,
            expected_current_token=current_token,
            prepared_document=prepared,
        )

    async def preview(
        self,
        *,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        current_token: str,
        target_id: str,
        actor_id: str,
        now: int | None = None,
    ) -> CurrentImportPreview:
        try:
            parent = await self.scope.authorize(requirement_id, actor_id)
            roots = await self._roots(requirement_id, kind, stage, current_token, actor_id, parent)
            result = await self.coordinator.preview(
                requirement_id=requirement_id,
                kind=kind,
                stage=stage,
                current_token=current_token,
                target_id=target_id,
                actor_id=actor_id,
                current_root_hashes=roots,
                secret=self.secret,
                now=now,
            )
            await self.session.rollback()  # read-only preview; release all locks
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

    async def execute(
        self,
        *,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        request: CurrentImportRequest,
        actor_id: str,
        now: int | None = None,
    ) -> dict[str, Any]:
        try:
            parent = await self.scope.authorize(requirement_id, actor_id)
            # A successful retry must not depend on a document or task that was
            # subsequently removed. It still requires current project permission.
            await self.session.rollback()
            await self.scope.lock_scope(requirement_id, actor_id, parent)
            replay = await self.coordinator.replay(
                requirement_id=requirement_id,
                kind=kind,
                stage=stage,
                request=request,
                actor_id=actor_id,
            )
            if replay is not None:
                await self.session.rollback()
                return replay
            roots = await self._roots(
                requirement_id, kind, stage, request.expected_current_token, actor_id, parent
            )
            result = await self.coordinator.execute(
                requirement_id=requirement_id,
                kind=kind,
                stage=stage,
                request=request,
                actor_id=actor_id,
                current_root_hashes=roots,
                secret=self.secret,
                now=now,
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
