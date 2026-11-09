"""Existing run response shapes projected from unified auxiliary executions."""

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrNotFound
from testing_agent.repositories.auxiliary_execution import (
    detail_row,
    history_rows,
    latest_rows_for_project,
)
from testing_agent.services.code_risk_analysis import parse_risk_report
from testing_agent.services.repository_profile import parse_repository_profile


def _duration(started: datetime | None, finished: datetime | None) -> int:
    if started is None or finished is None:
        return 0
    start = started if started.tzinfo else started.replace(tzinfo=UTC)
    end = finished if finished.tzinfo else finished.replace(tzinfo=UTC)
    return max(0, int((end - start).total_seconds() * 1000))


def _summary(row: Any) -> dict[str, Any]:
    status = row["status"]
    task_type = row["task_type"]
    current_stage = (
        "completed"
        if status == "success"
        else ("generate" if task_type == "test_order_graph" else "")
    )
    stage_status = "completed" if status == "success" else status if current_stage else ""
    return {
        "runId": row["execution_id"],
        "taskId": row["task_id"],
        "projectId": row["project_id"],
        "sprintId": row["sprint_id"],
        "requirementId": row["requirement_id"],
        "triggerUserId": row["requested_by"],
        "triggerType": row["trigger_type"] or "manual",
        "status": status,
        "workflowVersion": 2,
        "checkpointEnabled": False,
        "generationChainManaged": False,
        "currentStage": current_stage,
        "stageStatus": stage_status,
        "reviewStatus": "not_required" if task_type == "repository_profile" else "pending",
        "reviewerUserId": "",
        "reviewedAt": None,
        "reviewComment": "",
        "importStatus": "pending",
        "importedAt": None,
        "importedTargets": [],
        "durationMs": _duration(row["started_at"], row["finished_at"]),
        "errorMessage": row["error_message"] or "",
        "createdAt": row["created_at"],
        "startedAt": row["started_at"],
        "finishedAt": row["finished_at"],
        "updatedAt": row["finished_at"] or row["started_at"] or row["created_at"],
        "availableArtifacts": [],
        "hasResult": row["output_length"] > 0,
    }


async def auxiliary_history(
    session: AsyncSession, task_id: str, page: int, page_size: int
) -> dict[str, Any]:
    rows, counts, latest = await history_rows(session, task_id, page, page_size)
    return {
        "items": [_summary(row) for row in rows],
        "total": sum(counts.values()),
        "statusCounts": counts,
        "reviewPendingCount": 0,
        "latestRun": _summary(latest) if latest is not None else None,
    }


async def auxiliary_detail(session: AsyncSession, execution_id: str) -> dict[str, Any]:
    row = await detail_row(session, execution_id)
    if row is None:
        raise ErrNotFound()
    execution, task, attempt = row
    snapshot = attempt.input_snapshot_json or {}
    source = snapshot.get("source") or {}
    config = snapshot.get("config") or {}
    output = attempt.output_content or ""
    result = _summary(
        {
            "execution_id": execution.execution_id,
            "task_id": task.task_id,
            "project_id": task.project_id,
            "sprint_id": task.sprint_id,
            "requirement_id": task.requirement_id,
            "requested_by": execution.requested_by,
            "trigger_type": snapshot.get("triggerType"),
            "task_type": task.task_type,
            "status": attempt.status,
            "error_message": attempt.error_message,
            "created_at": execution.created_at,
            "started_at": attempt.started_at,
            "finished_at": attempt.finished_at,
            "output_length": len(output),
        }
    )
    result.update(
        {
            "snapshotJson": deepcopy(source),
            "configJson": deepcopy(config),
            "resultYaml": output,
            "resultSummaryJson": {},
        }
    )
    if task.task_type == "code_risk_analysis":
        result["report"] = parse_risk_report(output)
    if task.task_type == "repository_profile":
        result["profile"] = parse_repository_profile(output)
    return result


async def latest_project_run_summaries(
    session: AsyncSession, project_id: str, task_type: str
) -> list[dict[str, Any]]:
    """One summary per task of the requested type that has at least one execution."""
    rows = await latest_rows_for_project(session, project_id, task_type)
    return [_summary(row) for row in rows]
