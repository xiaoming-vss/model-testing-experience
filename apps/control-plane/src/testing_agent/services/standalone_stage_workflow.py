"""Existing functional checkpoint commands on execution-owned stage attempts."""

import json
from hashlib import sha256
from typing import Any

from testing_agent.core.errors import ErrBadRequest, ErrNotFound
from testing_agent.domain.ai_execution_format import FIELDS
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.repositories.standalone_execution import (
    dispatch_replay_records,
    workflow_records,
)
from testing_agent.services.ai_task_output import (
    dump_run,
    first_present,
    generated_function_cases,
    normalize_config_json,
    normalize_function_stage_config,
    validate_function_candidate_cases,
)
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


async def _task(service: StandaloneStageContext, run: StandaloneRun) -> AiGenerateTask:
    task = await service.repository.get_task_for_update(run.task_id)
    if task is None or task.requirement_id or task.task_type != "functional_case_generate":
        raise ErrNotFound()
    return task


async def _current_attempt(
    service: StandaloneStageContext, run: StandaloneRun, stage: str
) -> AiGenerationAttempt:
    records = await workflow_records(service.repository.session, run.run_id)
    if records is None:
        raise ErrNotFound()
    candidates = [attempt for name, attempt in records[2] if name == stage]
    if not candidates:
        raise ErrBadRequest()
    return max(candidates, key=lambda attempt: (attempt.attempt_no, attempt.id))


async def _connection(
    service: StandaloneStageContext,
    run: StandaloneRun,
    attempt: AiGenerationAttempt,
    body: dict[str, Any],
    user_id: str,
) -> str:
    previous = str((attempt.input_snapshot_json or {}).get("llmConnectionId") or "")
    return str(await service.stage_connection(run, body, user_id, previous))


def _request(service: StandaloneStageContext, body: dict[str, Any]) -> str:
    value = body.get("requestId")
    if value is not None and (
        not isinstance(value, str) or not value.strip() or len(value.strip()) > 64
    ):
        raise ErrBadRequest()
    return value.strip() if isinstance(value, str) else service.new_id()


async def _result(service: StandaloneStageContext, run_id: str) -> dict[str, Any]:
    await service.repository.commit()
    return dump_run(await project_standalone_execution(service.repository.session, run_id))


def _stage(run: StandaloneRun, body: dict[str, Any], *, final: bool = False) -> str:
    current = "detailed_cases" if run.current_stage == "completed" else run.current_stage
    requested = str(body.get("stage") or body.get("currentStage") or current)
    allowed = {"requirement_analysis", "case_names"}
    if final:
        allowed.add("detailed_cases")
    if requested != current or requested not in allowed:
        raise ErrBadRequest()
    return requested


async def _validated(
    service: StandaloneStageContext,
    run: StandaloneRun,
    stage: str,
    content: Any,
) -> tuple[str, str]:
    raw = json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else content
    if not isinstance(raw, str):
        raise ErrBadRequest()
    return await validate_generation_artifact(
        service.repository, "function", stage, raw, run.snapshot_json
    )


async def save_function_stage(
    service: StandaloneStageContext,
    run: StandaloneRun,
    body: dict[str, Any],
    user_id: str,
) -> dict[str, Any]:
    if (
        not run.checkpoint_enabled
        or run.status != "waiting_review"
        or run.import_status == "imported"
    ):
        raise ErrBadRequest()
    stage = _stage(run, body)
    if set(body) - {"stage", "currentStage", "configJson"} or "configJson" not in body:
        raise ErrBadRequest()
    field = FIELDS[stage]
    raw = normalize_config_json(body["configJson"])
    if (set(raw) & {"enhancedText", "requirementAnalysis", "caseNames"}) - {field}:
        raise ErrBadRequest()
    edits = normalize_function_stage_config(stage, raw)
    if set(edits) != {field}:
        raise ErrBadRequest()
    content, fmt = await _validated(service, run, stage, edits[field])
    task = await _task(service, run)
    _, _, previous = await lock_standalone_candidate(
        service.repository.session, task=task, execution_id=run.run_id, stage_name=stage
    )
    await save_standalone_draft(
        service.repository.session,
        task=task,
        execution_id=run.run_id,
        stage_name=stage,
        expected_attempt_id=previous.id,
        actor_id=user_id,
        content=content,
        output_format=fmt,
    )
    return await _result(service, run.run_id)


async def _review_replay(
    service: StandaloneStageContext, run: StandaloneRun, body: dict[str, Any], user_id: str
) -> dict[str, Any] | None:
    request_id = body.get("requestId")
    if request_id is None:
        return None
    request_id = _request(service, body)
    rows = await dispatch_replay_records(service.repository.session, request_id)
    if rows is None:
        return None
    dispatch, previous = rows
    if dispatch is None or previous is None:
        raise ErrBadRequest()
    queue, attempt, target_stage = dispatch
    prior, prior_stage = previous
    snapshot = attempt.input_snapshot_json or {}
    stage = str(body.get("stage") or body.get("currentStage") or prior_stage.stage)
    action = str(
        body.get("action")
        or body.get("reviewStatus")
        or body.get("status")
        or body.get("stageStatus")
        or "approve"
    )
    connection = body.get("connectionId") or body.get("llmConnectionId")
    expected_next = {"requirement_analysis": "case_names", "case_names": "detailed_cases"}.get(
        stage
    )
    if (
        queue.task_type != "functional_case_generate"
        or attempt.execution_id != run.run_id
        or attempt.requested_by != user_id
        or prior.execution_id != run.run_id
        or prior_stage.task_id != run.task_id
        or prior_stage.stage != stage
        or target_stage.task_id != run.task_id
        or target_stage.stage != expected_next
        or snapshot.get("dispatchOperation") != "advance"
        or prior.review_status != "approved"
        or prior.reviewer_user_id != user_id
        or (prior.review_comment or "")
        != str(body.get("reviewComment") or body.get("comment") or "")
        or action not in {"approve", "approved"}
        or (connection and connection != snapshot.get("llmConnectionId"))
    ):
        raise ErrBadRequest()
    return await _result(service, run.run_id)


async def review_function_stage(
    service: StandaloneStageContext,
    run: StandaloneRun,
    body: dict[str, Any],
    user_id: str,
) -> dict[str, Any]:
    replay = await _review_replay(service, run, body, user_id)
    if replay is not None:
        return replay
    if (
        not run.checkpoint_enabled
        or run.status != "waiting_review"
        or run.import_status == "imported"
    ):
        raise ErrBadRequest()
    stage = _stage(run, body)
    action = str(
        body.get("action")
        or body.get("reviewStatus")
        or body.get("status")
        or body.get("stageStatus")
        or "approve"
    )
    if action in {"approved", "approve"}:
        approved = True
    elif action in {"rejected", "reject"}:
        approved = False
    else:
        raise ErrBadRequest()
    task = await _task(service, run)
    _, _, attempt = await lock_standalone_candidate(
        service.repository.session, task=task, execution_id=run.run_id, stage_name=stage
    )
    if approved:
        await _validated(service, run, stage, attempt.output_content)
        connection_id = await _connection(service, run, attempt, body, user_id)
    async with service.repository.session.begin_nested():
        await review_standalone_candidate(
            service.repository.session,
            task=task,
            execution_id=run.run_id,
            stage_name=stage,
            expected_attempt_id=attempt.id,
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
                connection_id=connection_id,
                stage_name="case_names" if stage == "requirement_analysis" else "detailed_cases",
                operation="advance",
                expected_attempt_id=attempt.id,
                config={},
            )
    return await _result(service, run.run_id)


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
        encoded = json.dumps(
            {key: body[key] for key in keys if key in body},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ErrBadRequest() from exc
    return sha256(encoded.encode("utf-8")).hexdigest()


async def _revision_replay(
    service: StandaloneStageContext,
    run: StandaloneRun,
    body: dict[str, Any],
    user_id: str,
) -> dict[str, Any] | None:
    if body.get("requestId") is None:
        return None
    rows = await dispatch_replay_records(service.repository.session, _request(service, body))
    if rows is None:
        return None
    dispatch, previous = rows
    if dispatch is None or previous is None:
        raise ErrBadRequest()
    queue, attempt, target_stage = dispatch
    prior, prior_stage = previous
    snapshot = attempt.input_snapshot_json or {}
    if (
        queue.task_type != "functional_case_generate"
        or attempt.execution_id != run.run_id
        or attempt.requested_by != user_id
        or prior.execution_id != run.run_id
        or target_stage.task_id != run.task_id
        or prior_stage.task_id != run.task_id
        or target_stage.stage != prior_stage.stage
        or snapshot.get("dispatchOperation") != "revise"
        or snapshot.get("requestSignature") != _revision_signature(body)
    ):
        raise ErrBadRequest()
    return await _result(service, run.run_id)


async def revise_function_stage(
    service: StandaloneStageContext,
    run: StandaloneRun,
    body: dict[str, Any],
    user_id: str,
) -> dict[str, Any]:
    replay = await _revision_replay(service, run, body, user_id)
    if replay is not None:
        return replay
    stage = _stage(run, body, final=True)
    if run.import_status == "imported" or run.review_status != "pending":
        raise ErrBadRequest()
    if not (
        (run.checkpoint_enabled and run.status == "waiting_review" and stage != "detailed_cases")
        or (run.status == "success" and stage == "detailed_cases")
    ):
        raise ErrBadRequest()
    instruction = str(body.get("revisionInstruction") or "").strip()
    if not instruction:
        raise ErrBadRequest()
    task = await _task(service, run)
    _, _, attempt = await lock_standalone_candidate(
        service.repository.session, task=task, execution_id=run.run_id, stage_name=stage
    )
    connection_id = await _connection(service, run, attempt, body, user_id)
    async with service.repository.session.begin_nested():
        field = FIELDS.get(stage)
        candidate = None
        if field and "configJson" in body:
            edits = normalize_function_stage_config(stage, body["configJson"])
            if set(edits) != {field}:
                raise ErrBadRequest()
            candidate = edits[field]
        elif not field and "resultYaml" in body:
            candidate = body["resultYaml"]
        if candidate is not None:
            content, fmt = await _validated(service, run, stage, candidate)
            attempt = await save_standalone_draft(
                service.repository.session,
                task=task,
                execution_id=run.run_id,
                stage_name=stage,
                expected_attempt_id=attempt.id,
                actor_id=user_id,
                content=content,
                output_format=fmt,
            )
        attachments = await service.prepare_revision_attachments(user_id, run, body)
        config: dict[str, Any] = {}
        if attachments:
            config["revisionAttachments"] = list(attachments)
        await enqueue_standalone_attempt(
            service.repository.session,
            task=task,
            execution_id=run.run_id,
            request_id=_request(service, body),
            actor_id=user_id,
            connection_id=connection_id,
            stage_name=stage,
            operation="revise",
            expected_attempt_id=attempt.id,
            config=config,
            revision_instruction=instruction,
            request_signature=_revision_signature(body),
        )
    return await _result(service, run.run_id)


async def _retry_replay(
    service: StandaloneStageContext,
    run: StandaloneRun,
    body: dict[str, Any],
    user_id: str,
    *,
    graph: bool = False,
) -> dict[str, Any] | None:
    if body.get("requestId") is None:
        return None
    rows = await dispatch_replay_records(service.repository.session, _request(service, body))
    if rows is None:
        return None
    dispatch, previous = rows
    if dispatch is None or previous is None:
        raise ErrBadRequest()
    queue, attempt, target_stage = dispatch
    prior, prior_stage = previous
    snapshot = attempt.input_snapshot_json or {}
    stage = (
        "relation_analysis"
        if graph
        else str(body.get("stage") or body.get("currentStage") or prior_stage.stage)
    )
    connection = body.get("connectionId") or body.get("llmConnectionId")
    operation = snapshot.get("dispatchOperation")
    allowed_source = (
        (
            (
                operation == "advance"
                and prior_stage.stage == "detailed_cases"
                and prior.review_status == "approved"
            )
            or (
                operation == "retry"
                and prior_stage.stage == "relation_analysis"
                and prior.status in {"failed", "error"}
            )
        )
        if graph
        else (
            operation == "retry"
            and prior_stage.stage == stage
            and prior.status in {"failed", "error"}
        )
    )
    if (
        queue.task_type != "functional_case_generate"
        or attempt.execution_id != run.run_id
        or attempt.requested_by != user_id
        or prior.execution_id != run.run_id
        or target_stage.task_id != run.task_id
        or prior_stage.task_id != run.task_id
        or target_stage.stage != stage
        or not allowed_source
        or (connection and connection != snapshot.get("llmConnectionId"))
    ):
        raise ErrBadRequest()
    return await _result(service, run.run_id)


async def retry_function_stage(
    service: StandaloneStageContext,
    run: StandaloneRun,
    body: dict[str, Any],
    user_id: str,
) -> dict[str, Any]:
    replay = await _retry_replay(service, run, body, user_id)
    if replay is not None:
        return replay
    stage = _stage(run, body, final=True)
    if run.status not in {"failed", "error"} or run.import_status == "imported":
        raise ErrBadRequest()
    task = await _task(service, run)
    attempt = await _current_attempt(service, run, stage)
    connection_id = await _connection(service, run, attempt, body, user_id)
    await enqueue_standalone_attempt(
        service.repository.session,
        task=task,
        execution_id=run.run_id,
        request_id=_request(service, body),
        actor_id=user_id,
        connection_id=connection_id,
        stage_name=stage,
        operation="retry",
        expected_attempt_id=attempt.id,
    )
    return await _result(service, run.run_id)


async def generate_function_graph(
    service: StandaloneStageContext,
    run: StandaloneRun,
    body: dict[str, Any],
    user_id: str,
) -> dict[str, Any]:
    replay = await _retry_replay(service, run, body, user_id, graph=True)
    if replay is not None:
        return replay
    if run.review_status != "approved" or not (
        run.status == "success"
        or (run.status in {"failed", "error"} and run.current_stage == "relation_analysis")
    ):
        raise ErrBadRequest()
    cases = generated_function_cases(run)
    validate_function_candidate_cases(cases)
    case_ids = [str(first_present(case, "case_id", "caseId") or "").strip() for case in cases]
    if not cases or any(not case_id for case_id in case_ids) or len(case_ids) != len(set(case_ids)):
        raise ErrBadRequest()
    task = await _task(service, run)
    config: dict[str, Any] | None
    if run.status == "success":
        _, _, attempt = await lock_standalone_candidate(
            service.repository.session,
            task=task,
            execution_id=run.run_id,
            stage_name="detailed_cases",
        )
        operation, config = "advance", {}
    else:
        attempt = await _current_attempt(service, run, "relation_analysis")
        operation, config = "retry", None
    connection_id = await _connection(service, run, attempt, body, user_id)
    await enqueue_standalone_attempt(
        service.repository.session,
        task=task,
        execution_id=run.run_id,
        request_id=_request(service, body),
        actor_id=user_id,
        connection_id=connection_id,
        stage_name="relation_analysis",
        operation=operation,
        expected_attempt_id=attempt.id,
        config=config,
    )
    return await _result(service, run.run_id)
