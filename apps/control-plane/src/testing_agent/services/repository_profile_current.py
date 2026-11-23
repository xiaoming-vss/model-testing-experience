"""Read the adopted profile after checking its frozen material provenance."""

# transaction-bound: profile snapshot is checked under parent locks.

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.generation_root_fingerprints import IncompleteRootInput
from testing_agent.domain.generation_source_closure import RootSnapshot, SourceClosureError
from testing_agent.domain.repository_profile import parse_repository_profile
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
)
from testing_agent.repositories.generation_candidate_storage import candidate_stage_scope
from testing_agent.services.generation_application_scope import GenerationApplicationScope
from testing_agent.services.generation_chain import GenerationChainService
from testing_agent.services.generation_document_preparation import (
    lock_prepared_requirement_root,
    prepare_requirement_document,
)
from testing_agent.services.generation_source_errors import closure_error, source_error
from testing_agent.services.repository_profile_adoption import (
    PROFILE_KIND,
    PROFILE_STAGE,
    RepositoryProfileAdoption,
)


@dataclass(frozen=True)
class CurrentProfileSource:
    candidate_id: str
    snapshot_id: str
    current_token: str
    created_at: datetime
    profile: dict[str, Any]
    bindings: list[dict[str, Any]]


class RepositoryProfileCurrent:
    def __init__(self, chain: GenerationChainService) -> None:
        self.chain = chain
        self.session = chain.tasks.session
        self.scope = GenerationApplicationScope(chain, action="read")

    async def read(self, *, requirement_id: str, actor_id: str) -> CurrentProfileSource | None:
        """Return a verified profile source; never expose its internal bindings to the browser."""
        try:
            parent = await self.scope.authorize(requirement_id, actor_id)
            scope = await candidate_stage_scope(
                self.session, requirement_id=requirement_id, kind=PROFILE_KIND, stage=PROFILE_STAGE
            )
            if scope is None:
                await self.session.rollback()
                return None
            source_id = await self.session.scalar(
                select(AiGenerationStageContent.source_candidate_id).where(
                    AiGenerationStageContent.chain_id == scope[0],
                    AiGenerationStageContent.stage_id == scope[1],
                )
            )
            await self.session.rollback()
            if not source_id:
                return None
            if self.chain.files is None:
                raise dynamic_error(ErrBadRequest, "需求文件存储不可用")
            document = await prepare_requirement_document(
                self.session, requirement_id=requirement_id, files=self.chain.files
            )
            await self.session.rollback()
            await self.scope.lock_parents(requirement_id, actor_id, parent)
            root = await lock_prepared_requirement_root(self.session, prepared=document)
            result = await self.lock_verified(
                requirement_id=requirement_id, document_root=root, source_id=source_id
            )
            await self.session.rollback()
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

    async def lock_verified(
        self,
        *,
        requirement_id: str,
        document_root: RootSnapshot,
        source_id: str,
        expected: CurrentProfileSource | None = None,
    ) -> CurrentProfileSource:
        """Verify the adopted profile under the caller's parent locks.

        For a remote Git lookup, pass the previously verified profile as
        ``expected`` to prevent a changed profile or slot from reaching dispatch.
        The caller owns the transaction and must prepare and verify the document.
        """
        scope = await candidate_stage_scope(
            self.session, requirement_id=requirement_id, kind=PROFILE_KIND, stage=PROFILE_STAGE
        )
        if scope is None:
            raise SourceClosureError("concurrent_change")
        candidate = await self.session.scalar(
            select(AiGenerationCandidate)
            .where(
                AiGenerationCandidate.candidate_id == source_id,
                AiGenerationCandidate.chain_id == scope[0],
                AiGenerationCandidate.stage_id == scope[1],
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        slot = await self.session.scalar(
            select(AiGenerationStageContent)
            .where(
                AiGenerationStageContent.chain_id == scope[0],
                AiGenerationStageContent.stage_id == scope[1],
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if expected is not None and (
            candidate is None
            or slot is None
            or (candidate.candidate_id, candidate.snapshot_id, slot.content_token)
            != (expected.candidate_id, expected.snapshot_id, expected.current_token)
        ):
            raise SourceClosureError("concurrent_change")
        if (
            candidate is None
            or slot is None
            or slot.source_candidate_id != source_id
            or candidate.disposition != "available"
            or slot.invalidated_at is not None
            or slot.content != candidate.content
            or slot.format != candidate.format
            or slot.context_json != candidate.context_json
            or slot.source_attempt_id != candidate.current_attempt_id
            or slot.content_hash != candidate.content_hash
            or slot.basis_hash != candidate.basis_hash
            or slot.lineage_hash != candidate.lineage_hash
            or slot.source_manifest_json != candidate.source_manifest_json
            or slot.source_snapshot_json != candidate.source_snapshot_json
        ):
            raise SourceClosureError("source_stale")
        RepositoryProfileAdoption.validate_candidate(candidate, document_root=document_root)
        profile = parse_repository_profile(candidate.content)
        snapshot = candidate.source_snapshot_json or {}
        source = snapshot.get("source") or {}
        bindings = source.get("bindings") if isinstance(source, dict) else None
        if (
            profile is None
            or not isinstance(bindings, list)
            or any(not isinstance(item, dict) for item in bindings)
        ):
            raise SourceClosureError("source_unknown")
        return CurrentProfileSource(
            candidate_id=candidate.candidate_id,
            snapshot_id=candidate.snapshot_id,
            current_token=slot.content_token,
            created_at=candidate.created_at,
            profile=profile,
            bindings=deepcopy(bindings),
        )
