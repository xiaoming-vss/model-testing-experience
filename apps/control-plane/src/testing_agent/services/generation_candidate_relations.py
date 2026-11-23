"""Derived functional case graphs bound to a verified current candidate."""

# transaction-bound: parent, document, candidate closure and graph stage share one commit.

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.generation_root_fingerprints import IncompleteRootInput
from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.domain.project_policy import ProjectAction
from testing_agent.domain.request_identity import request_signature
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.generation_candidate_storage import candidate_stage_scope
from testing_agent.repositories.standalone_execution import lock_or_create_stage
from testing_agent.services.functional_requirement_source import (
    FUNCTIONAL_SOURCE_FORMAT,
    FUNCTIONAL_SOURCE_FORMAT_VERSION,
)
from testing_agent.services.generation_application_scope import GenerationApplicationScope
from testing_agent.services.generation_candidate_relation_source import (
    CandidateRelationSource,
    lock_candidate_relation_source,
)
from testing_agent.services.generation_chain import GenerationChainService
from testing_agent.services.generation_document_preparation import (
    lock_prepared_requirement_root,
    prepare_requirement_document,
)
from testing_agent.services.generation_source_errors import closure_error, source_error
from testing_agent.services.personal_authorization import require_personal_connection
from testing_agent.services.stage_storage.dispatch import (
    dispatch_stage_attempt,
    replay_stage_attempt,
)


class CandidateRelations:
    """Read or generate a graph only for the aligned adopted functional leaf."""

    def __init__(self, chain: GenerationChainService, *, action: ProjectAction) -> None:
        self.chain = chain
        self.session = chain.tasks.session
        self.scope = GenerationApplicationScope(chain, action=action)

    async def _source(
        self, requirement_id: str, token: str, prepared: Any
    ) -> CandidateRelationSource:
        root = await lock_prepared_requirement_root(self.session, prepared=prepared)
        return await lock_candidate_relation_source(
            self.session,
            requirement_id=requirement_id,
            expected_current_token=token,
            current_root_hashes={root.key: root.content_hash},
        )

    async def _task(self, requirement_id: str):
        scope = await candidate_stage_scope(
            self.session, requirement_id=requirement_id, kind="function", stage="detailed_cases"
        )
        if scope is None:
            raise SourceClosureError("pending_upstream")
        return scope[2]

    async def _replay(self, *, task: Any, actor_id: str, request_id: str, signature: str):
        worker = await self.session.scalar(
            select(WorkerTask).where(WorkerTask.domain == "ai", WorkerTask.task_id == request_id)
        )
        if worker is None:
            return None
        return await replay_stage_attempt(
            self.session,
            worker=worker,
            task=task,
            stage_name="relation_analysis",
            actor_id=actor_id,
            operation="generate",
            signature=signature,
        )

    async def run(
        self,
        *,
        requirement_id: str,
        current_token: str,
        connection_id: str,
        request_id: UUID,
        actor_id: str,
    ) -> dict[str, Any]:
        try:
            parent = await self.scope.authorize(requirement_id, actor_id)
            await require_personal_connection(
                self.session, actor_id, "llm", connection_id, parent.project_id
            )
            signature = request_signature(
                "candidate-relation-graph",
                {
                    "requirementId": requirement_id,
                    "currentToken": current_token,
                    "connectionId": connection_id,
                },
            )
            await self.session.rollback()
            await self.scope.lock_parents(requirement_id, actor_id, parent)
            task = await self._task(requirement_id)
            await require_personal_connection(
                self.session, actor_id, "llm", connection_id, parent.project_id
            )
            replay = await self._replay(
                task=task, actor_id=actor_id, request_id=str(request_id), signature=signature
            )
            if replay is not None:
                attempt_id = replay.id
                await self.session.rollback()
                return {"attemptId": attempt_id, "replayed": True}
            await self.session.rollback()
            if self.chain.files is None:
                raise dynamic_error(ErrBadRequest, "需求文件存储不可用")
            prepared = await prepare_requirement_document(
                self.session, requirement_id=requirement_id, files=self.chain.files
            )
            await self.session.rollback()
            await self.scope.lock_parents(requirement_id, actor_id, parent)
            task = await self._task(requirement_id)
            await require_personal_connection(
                self.session, actor_id, "llm", connection_id, parent.project_id
            )
            replay = await self._replay(
                task=task, actor_id=actor_id, request_id=str(request_id), signature=signature
            )
            if replay is not None:
                attempt_id = replay.id
                await self.session.rollback()
                return {"attemptId": attempt_id, "replayed": True}
            source = await self._source(requirement_id, current_token, prepared)
            stage, _ = await lock_or_create_stage(self.session, task.task_id, "relation_analysis")
            attempt, replayed = await dispatch_stage_attempt(
                self.session,
                task=task,
                stage_id=stage.id,
                request_id=str(request_id),
                actor_id=actor_id,
                input_snapshot={
                    "source": {
                        "sourceContent": source.material,
                        "sourceFormat": FUNCTIONAL_SOURCE_FORMAT,
                        "sourceFormatVersion": FUNCTIONAL_SOURCE_FORMAT_VERSION,
                    },
                    "config": {
                        "resultYaml": json.dumps({"cases": source.cases}, ensure_ascii=False)
                    },
                    "llmConnectionId": connection_id,
                    "candidateRelation": source.identity(),
                    "requestSignature": signature,
                },
                review_required=False,
            )
            attempt_id = attempt.id
            await self.session.commit()
            return {"attemptId": attempt_id, "replayed": replayed}
        except IncompleteRootInput as exc:
            await self.session.rollback()
            raise source_error("source_unknown") from exc
        except SourceClosureError as exc:
            await self.session.rollback()
            raise closure_error(exc) from exc
        except Exception:
            await self.session.rollback()
            raise

    async def view(
        self, *, requirement_id: str, current_token: str, actor_id: str
    ) -> dict[str, Any]:
        try:
            parent = await self.scope.authorize(requirement_id, actor_id)
            await self.session.rollback()
            if self.chain.files is None:
                raise dynamic_error(ErrBadRequest, "需求文件存储不可用")
            prepared = await prepare_requirement_document(
                self.session, requirement_id=requirement_id, files=self.chain.files
            )
            await self.session.rollback()
            await self.scope.lock_parents(requirement_id, actor_id, parent)
            task = await self._task(requirement_id)
            source = await self._source(requirement_id, current_token, prepared)
            attempts = list(
                (
                    await self.session.scalars(
                        select(AiGenerationAttempt)
                        .join(
                            AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id
                        )
                        .where(
                            AiGenerationStage.task_id == task.task_id,
                            AiGenerationStage.stage == "relation_analysis",
                        )
                        .order_by(
                            AiGenerationAttempt.created_at.desc(),
                            AiGenerationAttempt.attempt_no.desc(),
                        )
                    )
                ).all()
            )
            matching = [
                item
                for item in attempts
                if (item.input_snapshot_json or {}).get("candidateRelation") == source.identity()
            ]
            latest = matching[0] if matching else None
            successful = next(
                (item for item in matching if item.status == "success" and item.output_content),
                None,
            )
            result = {
                "candidateId": source.current.candidate_id,
                "snapshotId": source.current.snapshot_id,
                "currentToken": source.current.content_token,
                "sourceAttemptId": source.current.source_attempt_id,
                "resultYaml": source.current.content,
                "status": latest.status if latest else "not_started",
                "attemptId": latest.id if latest else None,
                "errorMessage": (latest.error_message or "") if latest else "",
                "caseRelations": json.loads(successful.output_content or "{}")
                if successful
                else None,
            }
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
