"""Render bounded stage attempt rows in the existing history response."""

from collections import defaultdict
from datetime import UTC
from typing import Any

from testing_agent.domain.ai_execution_format import FIELDS


def project_direct_history(rows, counts, pending, latest, imports) -> dict[str, Any]:
    sources: dict[str, list[Any]] = defaultdict(list)
    for item in imports:
        sources[item.version_id].append(item)

    def summarize(row: Any) -> dict[str, Any]:
        associated = sources.get(row.version_id, [])
        targets = list(dict.fromkeys((item.target_type, item.target_id) for item in associated))
        start, end = row.started_at, row.finished_at
        if start and end:
            start = start if start.tzinfo else start.replace(tzinfo=UTC)
            end = end if end.tzinfo else end.replace(tzinfo=UTC)
        duration = max(0, int((end - start).total_seconds() * 1000)) if start and end else 0
        field = FIELDS.get(row.stage)
        return {
            "runId": row.attempt_id,
            "taskId": row.task_id,
            "projectId": row.project_id,
            "sprintId": row.sprint_id,
            "requirementId": row.requirement_id,
            "triggerUserId": row.requested_by or "",
            "triggerType": "manual",
            "status": row.status,
            "workflowVersion": 2,
            "checkpointEnabled": True,
            "generationChainManaged": True,
            "currentStage": row.stage,
            "stageStatus": ("completed" if row.version_id else "waiting_review")
            if row.status == "success"
            else row.status,
            "reviewStatus": "approved"
            if row.version_id
            else "rejected"
            if row.invalidated_reason == "审核未通过，候选产物已丢弃"
            else "pending",
            "reviewerUserId": row.reviewer_user_id or "",
            "reviewedAt": row.reviewed_at,
            "reviewComment": row.review_comment or "",
            "importStatus": "imported" if associated else "pending",
            "importedTargets": [
                {"targetType": kind, "targetId": identity} for kind, identity in targets
            ],
            "importedAt": associated[-1].imported_at if associated else None,
            "durationMs": duration,
            "errorMessage": row.error_message or "",
            "createdAt": row.created_at,
            "startedAt": row.started_at,
            "finishedAt": row.finished_at,
            "updatedAt": row.finished_at or row.started_at or row.created_at,
            "availableArtifacts": [field] if field and row.output_length else [],
            "hasResult": bool(not field and row.output_length),
        }

    return {
        "items": [summarize(row) for row in rows],
        "total": sum(counts.values()),
        "statusCounts": counts,
        "reviewPendingCount": pending,
        "latestRun": summarize(latest) if latest else None,
    }
