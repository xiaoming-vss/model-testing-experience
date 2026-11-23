"""Check the current branch against a candidate's immutable UI source pin."""

# transaction-bound: recheck the candidate after remote GitLab reads.

from copy import deepcopy

from sqlalchemy import select

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.models.generation_candidates import AiGenerationCandidate
from testing_agent.repositories.generation_candidate_storage import candidate_stage_scope
from testing_agent.schemas.generation_candidates import CandidateUiSourceCheckRequest
from testing_agent.services.generation_application_scope import GenerationApplicationScope
from testing_agent.services.generation_chain import GenerationChainService
from testing_agent.services.generation_source_errors import closure_error


class UiCandidateSourceCheck:
    def __init__(self, chain: GenerationChainService) -> None:
        self.chain = chain
        self.session = chain.tasks.session
        self.scope = GenerationApplicationScope(chain, action="read")

    async def check(
        self,
        *,
        requirement_id: str,
        stage: str,
        candidate_id: str,
        request: CandidateUiSourceCheckRequest,
        actor_id: str,
    ) -> dict:
        try:
            self.chain.validate_stage("ui", stage)
            if self.chain.ui_sources is None:
                raise dynamic_error(ErrBadRequest, "UI 仓库源码解析未配置")
            parent = await self.scope.authorize(requirement_id, actor_id)
            scope = await candidate_stage_scope(
                self.session, requirement_id=requirement_id, kind="ui", stage=stage
            )
            if scope is None:
                raise SourceClosureError("source_unknown")
            candidate = await self.session.scalar(
                select(AiGenerationCandidate).where(
                    AiGenerationCandidate.chain_id == scope[0],
                    AiGenerationCandidate.stage_id == scope[1],
                    AiGenerationCandidate.candidate_id == candidate_id,
                )
            )
            if candidate is None:
                raise SourceClosureError("source_unknown")
            if candidate.candidate_token != request.expected_candidate_token:
                raise SourceClosureError("concurrent_change")
            if candidate.disposition != "available":
                raise SourceClosureError("source_stale")
            snapshot_id = candidate.snapshot_id
            snapshot = deepcopy(candidate.source_snapshot_json)
            source = snapshot.get("source") if isinstance(snapshot, dict) else None
            repository = source.get("sourceRepository") if isinstance(source, dict) else None
            bindings = source.get("bindings") if isinstance(source, dict) else None
            if (
                not isinstance(repository, dict)
                or not isinstance(bindings, list)
                or len(bindings) != 1
                or not isinstance(bindings[0], dict)
            ):
                raise SourceClosureError("source_unknown")
            await self.session.rollback()
            binding = await self.chain.ui_sources.rebind_frozen(
                repository=repository,
                binding=bindings[0],
                project_id=parent.project_id,
                user_id=actor_id,
                gitlab_connection_id=request.gitlab_connection_id,
            )
            access = await self.chain.ui_sources.resolve_binding_access(
                parent.project_id,
                actor_id,
                binding,
                gitlab_connection_id=binding["connectionId"],
            )
            head = await self.chain.ui_sources.resolve_latest_commit(
                parent.project_id,
                actor_id,
                repository["repositoryId"],
                repository["branch"],
                access,
            )
            await self.session.rollback()
            await self.scope.lock_parents(requirement_id, actor_id, parent)
            scope = await candidate_stage_scope(
                self.session, requirement_id=requirement_id, kind="ui", stage=stage
            )
            if scope is None:
                raise SourceClosureError("concurrent_change")
            candidate = await self.session.scalar(
                select(AiGenerationCandidate)
                .where(
                    AiGenerationCandidate.chain_id == scope[0],
                    AiGenerationCandidate.stage_id == scope[1],
                    AiGenerationCandidate.candidate_id == candidate_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if (
                candidate is None
                or candidate.snapshot_id != snapshot_id
                or candidate.candidate_token != request.expected_candidate_token
                or candidate.source_snapshot_json != snapshot
                or candidate.disposition != "available"
            ):
                raise SourceClosureError("concurrent_change")
            result = {
                "repositoryId": repository["repositoryId"],
                "branch": repository["branch"],
                "pinnedCommit": repository["commit"],
                "currentCommit": head,
                "changed": head != repository["commit"],
            }
            await self.session.rollback()
            return result
        except SourceClosureError as exc:
            await self.session.rollback()
            raise closure_error(exc) from exc
        except Exception:
            await self.session.rollback()
            raise
