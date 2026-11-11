"""Adapt one requirement-chain attempt to the established run-detail response."""

import json
from copy import deepcopy
from datetime import UTC
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrNotFound
from testing_agent.domain.ai_execution_format import FIELDS
from testing_agent.repositories.direct_attempt_view import direct_attempt_rows
from testing_agent.services.stage_storage.views import attempt_source
from testing_agent.services.ui_generation_sources import public_ui_source_snapshot


async def direct_attempt_view(
    session: AsyncSession, task_id: str, attempt_id: str
) -> dict[str, Any]:
    rows = await direct_attempt_rows(session, attempt_id, task_id)
    if rows is None:
        raise ErrNotFound()
    attempt, stage, task, version, imports = rows
    snapshot = attempt.input_snapshot_json or {}
    config = deepcopy(snapshot.get("config") or {}) if isinstance(snapshot, dict) else {}
    if not isinstance(config, dict):
        config = {}
    content = version.artifact_content if version else attempt.output_content or ""
    fmt = version.artifact_format if version else attempt.output_format
    field = FIELDS.get(stage.stage)
    result = ""
    if field and content:
        if fmt == "json":
            try:
                config[field] = json.loads(content)
            except ValueError:
                config[field] = content
        else:
            config[field] = content
    elif content:
        result = content
    targets = list(dict.fromkeys((item.target_type, item.target_id) for item in imports))
    started, finished = attempt.started_at, attempt.finished_at
    duration = 0
    if started and finished:
        start = started if started.tzinfo else started.replace(tzinfo=UTC)
        end = finished if finished.tzinfo else finished.replace(tzinfo=UTC)
        duration = max(0, int((end - start).total_seconds() * 1000))
    state = attempt.status
    stage_status = ("completed" if version else "waiting_review") if state == "success" else state
    public_source = attempt_source(attempt)
    if task.task_type == "ui_case_generate":
        public_source = public_ui_source_snapshot(public_source)
    return {
        "runId": attempt.id,
        "taskId": task.task_id,
        "projectId": task.project_id,
        "sprintId": task.sprint_id,
        "requirementId": task.requirement_id,
        "triggerUserId": attempt.requested_by or "",
        "triggerType": "manual",
        "status": state,
        "workflowVersion": 2,
        "checkpointEnabled": True,
        "generationChainManaged": True,
        "currentStage": stage.stage,
        "stageStatus": stage_status,
        "snapshotJson": public_source,
        "configJson": config,
        "resultYaml": result,
        "resultSummaryJson": deepcopy(attempt.output_context_json or {}),
        "errorMessage": attempt.error_message or "",
        "reviewStatus": "approved"
        if version
        else "rejected"
        if attempt.invalidated_reason == "审核未通过，候选产物已丢弃"
        else "pending",
        "reviewerUserId": version.reviewer_user_id if version else "",
        "reviewedAt": version.reviewed_at if version else None,
        "reviewComment": version.review_comment if version else "",
        "importStatus": "imported" if imports else "pending",
        "importedTargets": [
            {"targetType": kind, "targetId": identity} for kind, identity in targets
        ],
        "importedAt": imports[-1].imported_at if imports else None,
        "createdAt": attempt.created_at,
        "startedAt": started,
        "finishedAt": finished,
        "updatedAt": finished or started or attempt.created_at,
        "durationMs": duration,
        "hasResult": bool(result),
        "availableArtifacts": [key for key in FIELDS.values() if config.get(key)],
    }
