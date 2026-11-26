"""Transaction-scoped dispatch for a verified single-current candidate run."""

# transaction-bound: reservation, source locks and stage dispatch share one commit.

import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest
from testing_agent.db.savepoint import ensure_outer_transaction
from testing_agent.domain.generation_chain import HISTORICAL_REQUIREMENT_STAGE, HISTORICAL_STAGES
from testing_agent.domain.generation_source_closure import RootKey, RootSnapshot, SourceClosureError
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.generation_candidate_storage import candidate_stage_scope
from testing_agent.schemas.generation_candidates import CandidateRunRequest
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.generation_candidate_snapshot import (
    build_candidate_input_snapshot,
    candidate_request_signature,
)
from testing_agent.services.generation_source_selection import resolve_run_sources
from testing_agent.services.historical_requirement_inputs import build_historical_requirement_input
from testing_agent.services.historical_test_case_inputs import build_historical_test_case_input
from testing_agent.services.stage_storage.dispatch import (
    dispatch_stage_attempt,
    replay_stage_attempt,
    reserve_worker_identity,
)


@dataclass(frozen=True)
class CandidateDispatchResult:
    attempt: AiGenerationAttempt
    replayed: bool


async def replay_candidate_stage(
    session: AsyncSession,
    *,
    task: AiGenerateTask,
    kind: DesignKind,
    stage: str,
    request: CandidateRunRequest,
    actor_id: str,
) -> CandidateDispatchResult | None:
    """Replay an existing dispatch without rereading a document or reserving a worker.

    The caller must already authorize the actor, their connection and task and
    hold the parent locks. A matching receipt never starts another Worker.
    """
    if request.request_id is None:
        return None
    worker = await session.scalar(
        select(WorkerTask).where(
            WorkerTask.domain == "ai", WorkerTask.task_id == str(request.request_id)
        )
    )
    if worker is None:
        return None
    attempt = await replay_stage_attempt(
        session,
        worker=worker,
        task=task,
        stage_name=stage,
        actor_id=actor_id,
        operation="generate",
        signature=candidate_request_signature(
            requirement_id=task.requirement_id, kind=kind, stage=stage, request=request
        ),
    )
    return CandidateDispatchResult(attempt, True)


async def dispatch_candidate_stage(
    session: AsyncSession,
    *,
    task: AiGenerateTask,
    kind: DesignKind,
    stage: str,
    request: CandidateRunRequest,
    actor_id: str,
    source: dict[str, Any],
    current_root_hashes: dict[RootKey, str],
    direct_roots: tuple[RootSnapshot, ...],
) -> CandidateDispatchResult:
    """Reserve, resolve, freeze and dispatch in the caller's transaction.

    The caller must authorize the actor and personal connection, acquire parent
    business/task/stage locks in the established global order, and build source
    and root fingerprints from server-controlled data under those locks. Remote
    file/Git reads must happen before locking and be rechecked under the locks.
    No client-supplied source or root fingerprints are authoritative here.
    This function does not commit; all changes roll back together on failure.
    """
    if not task.requirement_id or not actor_id:
        raise ErrBadRequest()
    if stage in HISTORICAL_STAGES and request.generation_mode != "current":
        raise SourceClosureError("source_conflict")
    if (request.refresh_inputs or request.function_case_ids is not None) and (
        kind != "ui" or stage != "ui_surface"
    ):
        raise ErrBadRequest()
    if (request.source_repository_id or request.source_profile_candidate_id) and (
        kind != "ui" or stage != "ui_surface"
    ):
        raise ErrBadRequest()
    if request.gitlab_connection_id and kind != "ui":
        raise ErrBadRequest()
    if request.source_commit_mode != "profile" and (kind != "ui" or stage != "ui_surface"):
        raise ErrBadRequest()
    signature = candidate_request_signature(
        requirement_id=task.requirement_id, kind=kind, stage=stage, request=request
    )
    worker_id = str(request.request_id or uuid4())
    attempt_id = str(uuid4())
    await session.run_sync(ensure_outer_transaction)
    async with session.begin_nested():
        scope = await candidate_stage_scope(
            session, requirement_id=task.requirement_id, kind=kind, stage=stage
        )
        if scope is None or scope[2].task_id != task.task_id:
            raise SourceClosureError("source_unknown")
        worker, replay = await reserve_worker_identity(session, task, worker_id, attempt_id)
        if replay:
            attempt = await replay_stage_attempt(
                session,
                worker=worker,
                task=task,
                stage_name=stage,
                actor_id=actor_id,
                operation="generate",
                signature=signature,
            )
            return CandidateDispatchResult(attempt, True)
        sources = await resolve_run_sources(
            session,
            requirement_id=task.requirement_id,
            kind=kind,
            stage=stage,
            request=request,
            current_root_hashes=current_root_hashes,
            direct_roots=direct_roots,
        )
        if stage in HISTORICAL_STAGES:
            builder = (
                build_historical_requirement_input
                if stage == HISTORICAL_REQUIREMENT_STAGE
                else build_historical_test_case_input
            )
            history = await builder(
                session,
                project_id=task.project_id,
                requirement_id=task.requirement_id,
                sources=sources,
            )
            source = {
                **source,
                "sourceType": stage,
                "sourceContent": json.dumps(history, ensure_ascii=False, separators=(",", ":")),
            }
        snapshot = build_candidate_input_snapshot(
            requirement_id=task.requirement_id,
            kind=kind,
            stage=stage,
            request=request,
            sources=sources,
            source=source,
            attachment_hashes={},
        )
        attempt, reused = await dispatch_stage_attempt(
            session,
            task=task,
            stage_id=scope[1],
            request_id=worker_id,
            actor_id=actor_id,
            input_snapshot=snapshot,
            attempt_id=attempt_id,
            reserved_worker=worker,
            allow_multiple_candidates=True,
        )
        if reused:
            raise ErrBadRequest()
        return CandidateDispatchResult(attempt, False)
