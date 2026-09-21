"""Shared output contract for continuous and checkpoint execution."""

import json

from testing_agent_ai_worker.models.execution import TaskStatus
from testing_agent_ai_worker.models.task import Task
from testing_agent_ai_worker.tasks.result_summary import build_task_result_summary


def build_config_json(
    *,
    first_step_output: str,
    second_step_output: str | None = None,
) -> str:
    config = {
        "firstStepOutput": first_step_output,
    }
    if second_step_output is not None:
        config["secondStepOutput"] = second_step_output
    return json.dumps(config, ensure_ascii=False, indent=2)



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

