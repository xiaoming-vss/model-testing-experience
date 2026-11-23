"""Retain profile candidates independently of auxiliary execution history."""

# transaction-bound: Worker attempt and candidate are published atomically.

import json
from hashlib import sha256
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest
from testing_agent.domain.repository_profile import parse_repository_profile
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.generation_candidates import RequirementGenerationChain
from testing_agent.repositories.generation_candidate_creation import (
    CandidateCreationConflict,
    CandidateProvenance,
    create_candidate_from_successful_attempt,
)
from testing_agent.repositories.generation_current_chain import (
    ChainBindingConflict,
    bind_current_chain,
    ensure_empty_slot,
)
from testing_agent.schemas.requirement_design import DesignKind

PROFILE_CANDIDATE_PROTOCOL = "repository-profile-candidate/1"


async def ensure_profile_candidate_chain(
    session: AsyncSession, *, task: AiGenerateTask, stage: AiGenerationStage
) -> RequirementGenerationChain:
    """Bind the sole profile task; callers already hold the requirement and task locks."""
    if (
        task.task_type != "repository_profile"
        or not task.requirement_id
        or stage.task_id != task.task_id
        or stage.stage != "generate"
    ):
        raise ErrBadRequest()
    tasks = (
        await session.scalars(
            select(AiGenerateTask.task_id).where(
                AiGenerateTask.requirement_id == task.requirement_id,
                AiGenerateTask.task_type == "repository_profile",
            )
        )
    ).all()
    if len(tasks) != 1 or tasks[0] != task.task_id:
        from testing_agent.core.errors import dynamic_error

        raise dynamic_error(ErrBadRequest, "存在多个画像任务，请先完成历史配置转换")
    try:
        chain = await bind_current_chain(
            session,
            requirement_id=task.requirement_id,
            kind=cast(DesignKind, "repository_profile"),
            task_id=task.task_id,
        )
        await ensure_empty_slot(session, chain_id=chain.chain_id, stage_id=stage.id)
    except ChainBindingConflict as exc:
        raise ErrBadRequest() from exc
    return chain


def profile_candidate_basis(snapshot: dict[str, Any]) -> str:
    """Fingerprint the exact server-owned profile input, including repository pins."""
    try:
        encoded = json.dumps(
            snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise ErrBadRequest() from exc
    return f"sha256:{sha256(encoded.encode('utf-8')).hexdigest()}"


async def publish_profile_candidate(
    session: AsyncSession, *, stage: AiGenerationStage, attempt: AiGenerationAttempt
) -> None:
    """Append a profile candidate on successful completion, never adopt it implicitly."""
    snapshot = attempt.input_snapshot_json or {}
    protocol = snapshot.get("profileCandidateProtocol")
    if protocol is None:
        return
    source = snapshot.get("source")
    material = source.get("requirementMaterialCurrent") if isinstance(source, dict) else None
    if (
        protocol != PROFILE_CANDIDATE_PROTOCOL
        or stage.stage != "generate"
        or not isinstance(source, dict)
        or not isinstance(material, dict)
        or not all(
            isinstance(material.get(key), str) and material[key]
            for key in (
                "candidateId",
                "snapshotId",
                "currentToken",
                "taskId",
                "contentHash",
                "basisHash",
                "lineageHash",
                "documentRootHash",
            )
        )
        or parse_repository_profile(attempt.output_content) is None
    ):
        raise ErrBadRequest()
    chain = await session.scalar(
        select(RequirementGenerationChain).where(
            RequirementGenerationChain.task_id == stage.task_id,
            RequirementGenerationChain.kind == "repository_profile",
        )
    )
    if chain is None or source.get("requirementId") != chain.requirement_id:
        raise ErrBadRequest()
    try:
        await create_candidate_from_successful_attempt(
            session,
            chain_id=chain.chain_id,
            stage_id=stage.id,
            attempt_id=attempt.id,
            provenance=CandidateProvenance(
                generation_mode="current",
                source_manifest={"schemaVersion": PROFILE_CANDIDATE_PROTOCOL, "material": material},
                lineage_hash=material["lineageHash"],
                basis_hash=profile_candidate_basis(snapshot),
            ),
        )
    except CandidateCreationConflict as exc:
        raise ErrBadRequest() from exc
