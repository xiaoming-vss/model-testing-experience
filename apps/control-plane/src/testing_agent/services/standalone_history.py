"""Project independent execution history into existing paginated responses."""

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.ai_execution_format import FIELDS
from testing_agent.repositories.standalone_history import standalone_history_rows


def _utc(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


async def standalone_history(
    session: AsyncSession,
    task_id: str,
    page: int,
    page_size: int,
    pipeline_filter: str = "all",
) -> dict[str, Any]:
    rows, counts, pending, latest, artifacts, imports = await standalone_history_rows(
        session, task_id, page, page_size, pipeline_filter
    )
    fields: dict[str, set[str]] = defaultdict(set)
    for row in artifacts:
        if row.stage in FIELDS:
            fields[row.execution_id].add(FIELDS[row.stage])
    sources: dict[str, list[Any]] = defaultdict(list)
    for row in imports:
        sources[row.attempt_id].append(row)

    def summarize(row: Any) -> dict[str, Any]:
        associated = sources.get(row.final_attempt_id, [])
        targets = []
        seen = set()
        for entry in associated:
            key = (entry.target_type, entry.target_id)
            if key not in seen:
                targets.append({"targetType": key[0], "targetId": key[1]})
                seen.add(key)
        times = [
            _utc(row.created_at),
            _utc(row.started_at),
            _utc(row.finished_at),
            _utc(row.current_created),
        ]
        times.extend(_utc(entry.imported_at) for entry in associated)
        start, end = _utc(row.started_at), _utc(row.finished_at)
        duration = max(0, int((end - start).total_seconds() * 1000)) if start and end else 0
        current_status = row.current_status or ""
        stage_status = (
            "waiting_review"
            if current_status == "success" and row.workflow_status == "waiting_review"
            else "completed"
            if current_status == "success"
            else current_status
        )
        review = row.review_status or "pending"
        return {
            "runId": row.execution_id,
            "taskId": row.task_id,
            "projectId": row.project_id,
            "sprintId": row.sprint_id,
            "requirementId": row.requirement_id,
            "triggerUserId": row.requested_by,
            "triggerType": row.trigger_type or "manual",
            "status": row.workflow_status,
            "workflowVersion": 2,
            "checkpointEnabled": bool(row.checkpoint_enabled),
            "generationChainManaged": False,
            "currentStage": row.current_stage or "",
            "stageStatus": stage_status,
            "reviewStatus": "pending" if review == "not_required" else review,
            "reviewerUserId": row.reviewer_user_id or "",
            "reviewedAt": row.reviewed_at,
            "reviewComment": row.review_comment or "",
            "importStatus": "imported" if associated else "pending",
            "importedTargets": targets,
            "importedAt": associated[-1].imported_at if associated else None,
            "durationMs": duration,
            "errorMessage": row.current_error or "",
            "createdAt": row.created_at,
            "startedAt": row.started_at,
            "finishedAt": row.finished_at,
            "updatedAt": max((time for time in times if time is not None), default=None),
            "availableArtifacts": [
                field for field in FIELDS.values() if field in fields[row.execution_id]
            ],
            "hasResult": bool(row.has_result),
        }

    return {
        "items": [summarize(row) for row in rows],
        "total": sum(counts.values()),
        "statusCounts": counts,
        "reviewPendingCount": pending,
        "latestRun": summarize(latest) if latest is not None else None,
    }
