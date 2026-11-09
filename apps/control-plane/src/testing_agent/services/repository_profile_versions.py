"""Project successful repository profile attempts as immutable profile versions."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.services.repository_profile import parse_repository_profile


async def list_profile_versions(session: AsyncSession, task_id: str) -> list[dict[str, Any]]:
    """Return one version per successful profile execution, newest first.

    Profile versions are derived from immutable successful attempts. A failed or
    running attempt stays a run record and never consumes a version number.
    """
    rows = await session.scalars(
        select(AiGenerationAttempt)
        .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
        .where(
            AiGenerationStage.task_id == task_id,
            AiGenerationStage.stage == "generate",
            AiGenerationAttempt.status == "success",
            AiGenerationAttempt.output_content.is_not(None),
        )
        .order_by(
            func.coalesce(AiGenerationAttempt.finished_at, AiGenerationAttempt.created_at),
            AiGenerationAttempt.id,
        )
    )
    by_execution: dict[str, AiGenerationAttempt] = {}
    for attempt in rows:
        key = attempt.execution_id or attempt.id
        by_execution[key] = attempt

    versions: list[dict[str, Any]] = []
    for version_no, attempt in enumerate(by_execution.values(), start=1):
        content = attempt.output_content or ""
        snapshot = attempt.input_snapshot_json or {}
        source = snapshot.get("source") if isinstance(snapshot, dict) else {}
        understanding = (
            source.get("requirementUnderstandingVersion") if isinstance(source, dict) else None
        )
        source_run_id = attempt.execution_id or attempt.id
        versions.append(
            {
                "versionId": source_run_id,
                "versionNo": version_no,
                "label": f"v{version_no}",
                "profile": parse_repository_profile(content),
                "resultYaml": content,
                "sourceRunId": source_run_id,
                "requirementUnderstandingVersion": (
                    understanding if isinstance(understanding, dict) else None
                ),
                "createdAt": attempt.finished_at or attempt.created_at,
            }
        )
    versions.reverse()
    return versions


__all__ = ["list_profile_versions"]
