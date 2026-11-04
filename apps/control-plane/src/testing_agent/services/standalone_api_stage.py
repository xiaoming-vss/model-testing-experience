"""Checkpoint commands for independent two-stage API generation.

The caller authorizes and locks the execution before invoking these commands.
Each continuation retains the execution ID and creates its own Worker attempt.
"""

import json
from hashlib import sha256
from typing import Any

from testing_agent.core.errors import ErrBadRequest, ErrNotFound
from testing_agent.repositories.standalone_execution import (
    dispatch_replay_records,
    workflow_records,
)
from testing_agent.services.ai_task_output import dump_run, normalize_config_json
from testing_agent.services.generation_artifact_validation import validate_generation_artifact
from testing_agent.services.standalone_candidate import (
    lock_standalone_candidate,
    review_standalone_candidate,
    save_standalone_draft,
)
from testing_agent.services.standalone_dispatch import enqueue_standalone_attempt
from testing_agent.services.standalone_execution_view import project_standalone_execution
from testing_agent.services.standalone_run import StandaloneRun
from testing_agent.services.standalone_stage_context import StandaloneStageContext


def _request(service: StandaloneStageContext, body: dict[str, Any]) -> str:
    value = body.get("requestId")
    if value is not None and (
        not isinstance(value, str) or not value.strip() or len(value.strip()) > 64
    ):
        raise ErrBadRequest()
    return value.strip() if isinstance(value, str) else service.new_id()


async def _result(service: StandaloneStageContext, run: StandaloneRun) -> dict[str, Any]:
    await service.repository.commit()
    return dump_run(await project_standalone_execution(service.repository.session, run.run_id))


async def _replay(
    service: StandaloneStageContext,
    run: StandaloneRun,
    body: dict[str, Any],
    user_id: str,
    operation: str,
) -> dict[str, Any] | None:
    if body.get("requestId") is None:
        return None
    records = await dispatch_replay_records(service.repository.session, _request(service, body))
    if records is None:
        return None
    dispatch, predecessor = records
    if dispatch is None or predecessor is None:
        raise ErrBadRequest()
    queue, attempt, stage = dispatch
    prior, prior_stage = predecessor
    snapshot = attempt.input_snapshot_json or {}
    requested_stage = str(body.get("stage") or body.get("currentStage") or prior_stage.stage)
    connection = body.get("connectionId") or body.get("llmConnectionId")
    if (
        queue.task_type != "api_case_generate"
        or attempt.execution_id != run.run_id
        or attempt.requested_by != user_id
        or prior.execution_id != run.run_id
        or stage.task_id != run.task_id
        or prior_stage.task_id != run.task_id
        or prior_stage.stage != requested_stage
        or snapshot.get("dispatchOperation") != operation
        or (connection and connection != snapshot.get("llmConnectionId"))
    ):
        raise ErrBadRequest()
    if operation == "advance":
        action = str(
            body.get("action") or body.get("reviewStatus") or body.get("status") or "approve"
        )
        if (
            prior_stage.stage != "openapi_extract"
            or stage.stage != "generate"
            or prior.review_status != "approved"
            or prior.reviewer_user_id != user_id
            or (prior.review_comment or "")
            != str(body.get("reviewComment") or body.get("comment") or "")
            or action not in {"approve", "approved"}
        ):
            raise ErrBadRequest()
    elif operation == "revise":
        if (
            stage.stage != prior_stage.stage
            or prior.status != "success"
            or snapshot.get("requestSignature") != _revision_signature(body)
        ):
            raise ErrBadRequest()
    elif stage.stage != prior_stage.stage or prior.status not in {"failed", "error"}:
        raise ErrBadRequest()
    return await _result(service, run)


def _revision_signature(body: dict[str, Any]) -> str:
    keys = (
        "stage",
        "currentStage",
        "revisionInstruction",
        "configJson",
        "resultYaml",
        "attachmentFileIds",
        "connectionId",
        "llmConnectionId",
    )
    try:
        value = json.dumps(
            {key: body[key] for key in keys if key in body},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ErrBadRequest() from exc
    return sha256(value.encode("utf-8")).hexdigest()


async def _candidate_content(
    service: StandaloneStageContext, run: StandaloneRun, stage: str, body: dict[str, Any]
) -> tuple[str, str] | None:
    if (stage == "openapi_extract" and "resultYaml" in body) or (
        stage == "generate" and "configJson" in body
    ):
        raise ErrBadRequest()
    if stage == "openapi_extract" and "configJson" in body:
        edits = normalize_config_json(body["configJson"])
        if set(edits) != {"apiExtraction"}:
            raise ErrBadRequest()
        raw = edits["apiExtraction"]
        raw = json.dumps(raw, ensure_ascii=False) if isinstance(raw, dict) else raw
    elif stage == "generate" and "resultYaml" in body:
        raw = body["resultYaml"]
    else:
        return None
    if not isinstance(raw, str):
        raise ErrBadRequest()
    return await validate_generation_artifact(
        service.repository, "api", stage, raw, run.snapshot_json
    )


async def save_api_checkpoint(
    service: StandaloneStageContext, run: StandaloneRun, body: dict[str, Any], user_id: str
) -> dict[str, Any]:
    if (
        not run.checkpoint_enabled
        or run.status != "waiting_review"
        or run.current_stage != "openapi_extract"
        or str(body.get("stage") or body.get("currentStage") or "openapi_extract")
        != "openapi_extract"
        or set(body) - {"stage", "currentStage", "configJson"}
        or run.snapshot_json.get("apiWorkflowVersion") != "api_two_stage/1.0"
    ):
        raise ErrBadRequest()
    content = await _candidate_content(service, run, "openapi_extract", body)
    if content is None:
        raise ErrBadRequest()
    task = await service.repository.get_task_for_update(run.task_id)
    if task is None or task.requirement_id or task.task_type != "api_case_generate":
        raise ErrNotFound()
    _, _, candidate = await lock_standalone_candidate(
        service.repository.session, task=task, execution_id=run.run_id, stage_name="openapi_extract"
    )
    await save_standalone_draft(
        service.repository.session,
        task=task,
        execution_id=run.run_id,
        stage_name="openapi_extract",
        expected_attempt_id=candidate.id,
        actor_id=user_id,
        content=content[0],
        output_format=content[1],
    )
    return await _result(service, run)


async def revise_api_stage(
    service: StandaloneStageContext, run: StandaloneRun, body: dict[str, Any], user_id: str
) -> dict[str, Any]:
    replay = await _replay(service, run, body, user_id, "revise")
    if replay is not None:
        return replay
    stage = "generate" if run.current_stage == "completed" else run.current_stage
    if (
        not run.checkpoint_enabled
        or stage not in {"openapi_extract", "generate"}
        or str(body.get("stage") or body.get("currentStage") or stage) != stage
        or not (
            (stage == "openapi_extract" and run.status == "waiting_review")
            or (stage == "generate" and run.status == "success")
        )
        or run.review_status != "pending"
        or run.import_status == "imported"
        or run.snapshot_json.get("apiWorkflowVersion") != "api_two_stage/1.0"
    ):
        raise ErrBadRequest()
    instruction = str(body.get("revisionInstruction") or "").strip()
    if not instruction:
        raise ErrBadRequest()
    task = await service.repository.get_task_for_update(run.task_id)
    if task is None or task.requirement_id or task.task_type != "api_case_generate":
        raise ErrNotFound()
    _, _, candidate = await lock_standalone_candidate(
        service.repository.session, task=task, execution_id=run.run_id, stage_name=stage
    )
    previous = str((candidate.input_snapshot_json or {}).get("llmConnectionId") or "")
    connection = str(await service.stage_connection(run, body, user_id, previous))
    async with service.repository.session.begin_nested():
        content = await _candidate_content(service, run, stage, body)
        if content is not None:
            candidate = await save_standalone_draft(
                service.repository.session,
                task=task,
                execution_id=run.run_id,
                stage_name=stage,
                expected_attempt_id=candidate.id,
                actor_id=user_id,
                content=content[0],
                output_format=content[1],
            )
        attachments = await service.prepare_revision_attachments(user_id, run, body)
        config = {"revisionAttachments": list(attachments)} if attachments else {}
        await enqueue_standalone_attempt(
            service.repository.session,
            task=task,
            execution_id=run.run_id,
            request_id=_request(service, body),
            actor_id=user_id,
            connection_id=connection,
            stage_name=stage,
            operation="revise",
            expected_attempt_id=candidate.id,
            config=config,
            revision_instruction=instruction,
            request_signature=_revision_signature(body),
        )
    return await _result(service, run)


async def review_api_checkpoint(
    service: StandaloneStageContext, run: StandaloneRun, body: dict[str, Any], user_id: str
) -> dict[str, Any]:
    replay = await _replay(service, run, body, user_id, "advance")
    if replay is not None:
        return replay
    if (
        not run.checkpoint_enabled
        or run.status != "waiting_review"
        or run.current_stage != "openapi_extract"
        or str(body.get("stage") or body.get("currentStage") or "openapi_extract")
        != "openapi_extract"
        or run.snapshot_json.get("apiWorkflowVersion") != "api_two_stage/1.0"
    ):
        raise ErrBadRequest()
    action = str(body.get("action") or body.get("reviewStatus") or body.get("status") or "approve")
    if action not in {"approve", "approved", "reject", "rejected"}:
        raise ErrBadRequest()
    approved = action in {"approve", "approved"}
    task = await service.repository.get_task_for_update(run.task_id)
    if task is None or task.requirement_id or task.task_type != "api_case_generate":
        raise ErrNotFound()
    _, _, candidate = await lock_standalone_candidate(
        service.repository.session, task=task, execution_id=run.run_id, stage_name="openapi_extract"
    )
    if approved:
        await validate_generation_artifact(
            service.repository,
            "api",
            "openapi_extract",
            candidate.output_content or "",
            run.snapshot_json,
        )
        previous = str((candidate.input_snapshot_json or {}).get("llmConnectionId") or "")
        connection = str(await service.stage_connection(run, body, user_id, previous))
    async with service.repository.session.begin_nested():
        await review_standalone_candidate(
            service.repository.session,
            task=task,
            execution_id=run.run_id,
            stage_name="openapi_extract",
            expected_attempt_id=candidate.id,
            actor_id=user_id,
            approved=approved,
            comment=str(body.get("reviewComment") or body.get("comment") or ""),
        )
        if approved:
            await enqueue_standalone_attempt(
                service.repository.session,
                task=task,
                execution_id=run.run_id,
                request_id=_request(service, body),
                actor_id=user_id,
                connection_id=connection,
                stage_name="generate",
                operation="advance",
                expected_attempt_id=candidate.id,
                config={},
            )
    return await _result(service, run)


async def retry_api_stage(
    service: StandaloneStageContext, run: StandaloneRun, body: dict[str, Any], user_id: str
) -> dict[str, Any]:
    replay = await _replay(service, run, body, user_id, "retry")
    if replay is not None:
        return replay
    stage = str(body.get("stage") or body.get("currentStage") or run.current_stage)
    if (
        not run.checkpoint_enabled
        or run.status not in {"failed", "error"}
        or stage != run.current_stage
        or stage not in {"openapi_extract", "generate"}
        or run.snapshot_json.get("apiWorkflowVersion") != "api_two_stage/1.0"
    ):
        raise ErrBadRequest()
    task = await service.repository.get_task_for_update(run.task_id)
    if task is None or task.requirement_id or task.task_type != "api_case_generate":
        raise ErrNotFound()
    records = await workflow_records(service.repository.session, run.run_id)
    candidates = [attempt for name, attempt in records[2] if name == stage] if records else []
    if not candidates:
        raise ErrBadRequest()
    candidate = max(candidates, key=lambda item: (item.attempt_no, item.id))
    previous = str((candidate.input_snapshot_json or {}).get("llmConnectionId") or "")
    connection = str(await service.stage_connection(run, body, user_id, previous))
    await enqueue_standalone_attempt(
        service.repository.session,
        task=task,
        execution_id=run.run_id,
        request_id=_request(service, body),
        actor_id=user_id,
        connection_id=connection,
        stage_name=stage,
        operation="retry",
        expected_attempt_id=candidate.id,
    )
    return await _result(service, run)
