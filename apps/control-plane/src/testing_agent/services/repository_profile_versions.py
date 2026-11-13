"""Project successful repository profile attempts as immutable profile versions."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.services.repository_profile import parse_repository_profile


async def _profile_attempts(
    session: AsyncSession, task_id: str
) -> list[tuple[int, AiGenerationAttempt]]:
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
    return list(enumerate(by_execution.values(), start=1))


async def list_profile_version_records(
    session: AsyncSession, task_id: str, *, include_bindings: bool = False
) -> list[dict[str, Any]]:
    """Return immutable version records, newest first.

    ``include_bindings`` is internal only: bindings carry clone URLs and the
    profile runner's connection IDs and must never reach a browser response.
    """
    versions: list[dict[str, Any]] = []
    for version_no, attempt in await _profile_attempts(session, task_id):
        content = attempt.output_content or ""
        snapshot = attempt.input_snapshot_json or {}
        source = snapshot.get("source") if isinstance(snapshot, dict) else {}
        material = source.get("requirementMaterialVersion") if isinstance(source, dict) else None
        source_run_id = attempt.execution_id or attempt.id
        record = {
            "versionId": source_run_id,
            "versionNo": version_no,
            "label": f"v{version_no}",
            "profile": parse_repository_profile(content),
            "resultYaml": content,
            "sourceRunId": source_run_id,
            "requirementMaterialVersion": (material if isinstance(material, dict) else None),
            "createdAt": attempt.finished_at or attempt.created_at,
        }
        if include_bindings:
            bindings = source.get("bindings") if isinstance(source, dict) else None
            record["bindings"] = (
                [deepcopy(binding) for binding in bindings if isinstance(binding, dict)]
                if isinstance(bindings, list)
                else []
            )
        versions.append(record)
    versions.reverse()
    return versions


async def list_profile_versions(session: AsyncSession, task_id: str) -> list[dict[str, Any]]:
    """Return one version per successful profile execution, newest first.

    Profile versions are derived from immutable successful attempts. A failed or
    running attempt stays a run record and never consumes a version number.
    """
    return await list_profile_version_records(session, task_id)


__all__ = ["list_profile_version_records", "list_profile_versions"]
