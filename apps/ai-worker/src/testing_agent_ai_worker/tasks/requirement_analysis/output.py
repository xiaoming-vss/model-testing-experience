"""Shared output contract for continuous and checkpoint execution."""

import json

from testing_agent_ai_worker.models.execution import TaskStatus
from testing_agent_ai_worker.models.task import Task
from testing_agent_ai_worker.tasks.result_summary import build_task_result_summary


def build_config_json(
    *,
    first_step_output: str | dict,
) -> str:
    config = {
        "firstStepOutput": first_step_output,
    }
    return json.dumps(config, ensure_ascii=False, indent=2)


def build_review_config_json(*, review_output: dict) -> str:
    """Keep the review report in the stage-owned config field."""
    return json.dumps({"reviewOutput": review_output}, ensure_ascii=False, indent=2)


def build_review_summary(artifact: dict) -> dict[str, int | str]:
    """Stable counts for the review stage result summary."""
    issues = artifact.get("issues") or []
    return {
        "reviewStatus": str(artifact.get("reviewStatus") or ""),
        "issueCount": len(issues),
        "blockerCount": sum(
            1 for issue in issues if issue.get("severity") == "blocker"
        ),
        "majorCount": sum(1 for issue in issues if issue.get("severity") == "major"),
        "minorCount": sum(1 for issue in issues if issue.get("severity") == "minor"),
    }


def build_result_summary_json(
    *,
    task: Task,
    status: TaskStatus | str,
    config_json: str,
    output_yaml: str,
    error_message: str | None,
) -> str:
    return build_task_result_summary(
        task=task,
        status=status,
        error_message=error_message,
        details={
            "sourceType": task.payload.source_type,
            "documentType": task.payload.document_type,
            "configJsonLength": len(config_json),
            "resultLength": len(output_yaml),
        },
    )
