"""Worker payload from a stage-owned frozen attempt."""

import json
from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from testing_agent.core.errors import ErrBadRequest
from testing_agent.domain.ai_tasks import AUXILIARY_EXECUTION_TYPES
from testing_agent.domain.generation_chain import HISTORICAL_STAGES
from testing_agent.models.worker_task import WorkerTask
from testing_agent.schemas.generation_candidates import FrozenCandidateInput
from testing_agent.services.stage_storage.authorization import DirectWorkerAuthority


def worker_payloads(
    authority: DirectWorkerAuthority,
    worker_task: WorkerTask,
    *,
    stage_name: str,
    lease_seconds: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Prepare existing claim and snapshot shapes without reading the old run ledger."""
    snapshot = authority.input_snapshot
    source = snapshot.get("source") or {}
    config = snapshot.get("config") or {}
    llm_connection_id = snapshot.get("llmConnectionId")
    if (
        not isinstance(source, dict)
        or not isinstance(config, dict)
        or not isinstance(llm_connection_id, str)
        or not llm_connection_id
    ):
        raise ErrBadRequest()
    config = deepcopy(config)
    config.pop("revisionInstruction", None)
    if authority.revision_instruction:
        config["revisionInstruction"] = authority.revision_instruction
    task = authority.task
    auxiliary = task.task_type in AUXILIARY_EXECUTION_TYPES
    worker_stage = stage_name if not auxiliary or task.task_type == "test_order_graph" else ""
    run = deepcopy(source)
    run.pop("runId", None)
    run.setdefault("name", task.name)
    run.update(
        {
            "taskId": task.task_id,
            "attemptId": authority.attempt_id,
            "taskType": task.task_type,
            "projectId": task.project_id,
            "sprintId": task.sprint_id,
            "requirementId": task.requirement_id,
        }
    )
    document_type = run.get("documentType") or run.get("sourceType")
    if stage_name in HISTORICAL_STAGES:
        for key in (
            "documentFileId",
            "documentHash",
            "documentType",
            "documentFilename",
            "attachmentHashes",
        ):
            run.pop(key, None)
    elif task.task_type == "requirement_analysis" and document_type in {
        "text",
        "word",
        "docx",
        "richtext",
    }:
        url = f"/internal/ai-worker/tasks/{worker_task.task_id}/requirement-document"
        run["documentDownloadUrl"] = url
        if document_type in {"word", "docx"} and not run.get("sourceContent"):
            run["sourceContent"] = url
    if task.task_type == "ui_case_generate":
        run["gitlabCredentialsUrl"] = (
            f"/internal/ai-worker/tasks/{worker_task.task_id}/gitlab-credentials"
        )
    config_text = json.dumps(config, ensure_ascii=False)
    claim = {
        "taskId": worker_task.task_id,
        "taskType": task.task_type,
        "attemptId": authority.attempt_id,
        "generateTaskId": task.task_id,
        "projectId": task.project_id,
        "sprintId": task.sprint_id,
        "requirementId": task.requirement_id,
        "llmConnectionId": llm_connection_id,
        "checkpointEnabled": not auxiliary,
        "currentStage": worker_stage,
        "leaseSeconds": lease_seconds,
        "configJson": config_text,
    }
    detailed = {
        "taskType": task.task_type,
        "checkpointEnabled": not auxiliary,
        "currentStage": worker_stage,
        "configJson": config_text,
        "run": run,
    }
    protocol = snapshot.get("candidateProtocol")
    if protocol is not None:
        if protocol not in {"single-current/1", "single-current/2"}:
            raise ErrBadRequest()
        try:
            candidate_input = FrozenCandidateInput.model_validate(snapshot.get("candidateInput"))
        except ValidationError as exc:
            raise ErrBadRequest() from exc
        # Revision ancestry is a control-plane concern; Worker still receives
        # the same frozen candidate input contract and existing revision fields.
        detailed["candidateProtocol"] = "single-current/1"
        detailed["candidateInput"] = candidate_input.model_dump(mode="json", by_alias=True)
    return claim, detailed
