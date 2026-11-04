"""Validate and apply independent workflow Worker results in one transaction."""

import json
from copy import deepcopy
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest
from testing_agent.domain.ai_execution_format import FIELDS, final_review_stage
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.schemas.workers import WorkerProgressRequest, WorkerTaskEventRequest
from testing_agent.services.generation_artifact_validation import validate_generation_artifact
from testing_agent.services.stage_storage.worker_events import validate_relation_output
from testing_agent.services.standalone_execution import workflow_stage_names
from testing_agent.services.standalone_worker_transitions import StandaloneWorkerTransitions
from testing_agent.services.worker_domains.events import final_run_status


def _kind(task: AiGenerateTask) -> DesignKind:
    mapping = {
        "functional_case_generate": "function",
        "api_case_generate": "api",
        "ui_case_generate": "ui",
    }
    if task.task_type not in mapping:
        raise ErrBadRequest()
    return cast(DesignKind, mapping[task.task_type])


def _config(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ErrBadRequest()
    return value


def _frozen(attempt: AiGenerationAttempt) -> dict[str, Any]:
    value = (attempt.input_snapshot_json or {}).get("config") or {}
    if not isinstance(value, dict):
        raise ErrBadRequest()
    return value


def _check_upstream(
    names: list[str], stage: str, frozen: dict[str, Any], supplied: dict[str, Any]
) -> None:
    if stage not in names:
        raise ErrBadRequest()
    for prior in names[: names.index(stage)]:
        field = FIELDS.get(prior)
        if field and supplied.get(field) is not None and supplied[field] != frozen.get(field):
            raise ErrBadRequest()


async def _validate(
    session: AsyncSession, task: AiGenerateTask, stage: str, source: dict[str, Any], value: Any
) -> tuple[str, str]:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    if not isinstance(value, str):
        raise ErrBadRequest()
    return await validate_generation_artifact(
        AiGenerateTaskRepository(session), _kind(task), stage, value, source
    )


async def _move_to(
    session: AsyncSession,
    task: AiGenerateTask,
    queue: WorkerTask,
    target: str,
    supplied: dict[str, Any],
) -> tuple[Any, Any, AiGenerationAttempt]:
    """Advance a continuous dispatch using validated intermediate artifacts only."""
    transitions = StandaloneWorkerTransitions(session)
    execution, stage, attempt = await transitions.current(task, queue)
    source = execution.source_snapshot_json or {}
    names = workflow_stage_names(task.task_type, source)
    final = final_review_stage(task.task_type, names)
    if target not in names or target == "relation_analysis" or stage.stage not in names:
        raise ErrBadRequest()
    if names.index(target) < names.index(stage.stage) or names.index(target) > names.index(final):
        raise ErrBadRequest()
    while stage.stage != target:
        field = FIELDS.get(stage.stage)
        frozen = _frozen(attempt)
        _check_upstream(names, stage.stage, frozen, supplied)
        candidate = supplied.get(field) if field else None
        if candidate is not None:
            content, output_format = await _validate(session, task, stage.stage, source, candidate)
            if attempt.output_content:
                if output_format == attempt.output_format == "json":
                    if json.loads(attempt.output_content) != json.loads(content):
                        raise ErrBadRequest()
                elif attempt.output_content != content:
                    raise ErrBadRequest()
        elif attempt.output_content:
            content, output_format = attempt.output_content, attempt.output_format or "json"
        else:
            raise ErrBadRequest()
        next_config = deepcopy(frozen)
        if field:
            next_config[field] = json.loads(content) if output_format == "json" else content
        next_name = names[names.index(stage.stage) + 1]
        await transitions.advance(
            task,
            queue,
            next_stage=next_name,
            content=content,
            output_format=output_format,
            next_config=next_config,
        )
        execution, stage, attempt = await transitions.current(task, queue)
    return execution, stage, attempt


async def apply_standalone_progress(
    session: AsyncSession, task: AiGenerateTask, queue: WorkerTask, body: WorkerProgressRequest
) -> bool:
    """Apply a checked checkpoint or intermediate artifact; return whether dispatch ended."""
    if (body.task_id and body.task_id != queue.task_id) or (
        body.run_id and body.run_id != queue.run_id
    ):
        raise ErrBadRequest()
    if body.stage_status not in {None, "", "running", "waiting_review"}:
        raise ErrBadRequest()
    supplied = _config(body.config_json)
    transitions = StandaloneWorkerTransitions(session)
    execution, stage, attempt = await transitions.current(task, queue)
    if attempt.status != "running":
        raise ErrBadRequest()
    source = execution.source_snapshot_json or {}
    names = workflow_stage_names(task.task_type, source)
    final = final_review_stage(task.task_type, names)
    reported = body.current_stage or stage.stage
    legacy_api = task.task_type == "api_case_generate" and names == ["generate"]
    if legacy_api and reported in {"openapi_extract", "api_case_generating"}:
        reported = "generate"
    if (
        not execution.checkpoint_enabled
        and reported in names
        and stage.stage in names
        and names.index(reported) < names.index(stage.stage)
    ):
        # An acknowledgement may have been lost after an earlier stage advanced.
        # Accept only a replay belonging to this dispatch and never change state.
        prior = await session.scalar(
            select(AiGenerationAttempt)
            .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
            .where(
                AiGenerationAttempt.execution_id == execution.execution_id,
                AiGenerationAttempt.worker_task_id == queue.task_id,
                AiGenerationAttempt.status == "success",
                AiGenerationStage.task_id == task.task_id,
                AiGenerationStage.stage == reported,
            )
        )
        if prior is None or body.stage_status == "waiting_review":
            raise ErrBadRequest()
        _check_upstream(names, reported, _frozen(prior), supplied)
        field = FIELDS.get(reported)
        candidate = supplied.get(field) if field else None
        if candidate is not None:
            content, output_format = await _validate(session, task, reported, source, candidate)
            if output_format == prior.output_format == "json":
                if json.loads(content) != json.loads(prior.output_content or "null"):
                    raise ErrBadRequest()
            elif content != prior.output_content:
                raise ErrBadRequest()
        return False
    if not execution.checkpoint_enabled and reported != stage.stage:
        execution, stage, attempt = await _move_to(session, task, queue, reported, supplied)
    if reported != stage.stage:
        raise ErrBadRequest()
    frozen = _frozen(attempt)
    _check_upstream(names, stage.stage, frozen, supplied)
    field = FIELDS.get(stage.stage)
    candidate = supplied.get(field) if field else None
    if body.stage_status == "waiting_review":
        if not execution.checkpoint_enabled or stage.stage == final or candidate is None:
            raise ErrBadRequest()
        content, output_format = await _validate(session, task, stage.stage, source, candidate)
        await transitions.completed(task, queue, content=content, output_format=output_format)
        return True
    if candidate is not None and not execution.checkpoint_enabled:
        content, output_format = await _validate(session, task, stage.stage, source, candidate)
        attempt.output_content, attempt.output_format = content, output_format
        await session.flush()
    return False


async def apply_standalone_completion(
    session: AsyncSession, task: AiGenerateTask, queue: WorkerTask, body: WorkerTaskEventRequest
) -> str:
    """Apply the final candidate or failure without replacing any earlier result."""
    if (body.task_id and body.task_id != queue.task_id) or (
        body.run_id and body.run_id != queue.run_id
    ):
        raise ErrBadRequest()
    snapshot = body.snapshot_json or {}
    if not isinstance(snapshot, dict):
        raise ErrBadRequest()
    transitions = StandaloneWorkerTransitions(session)
    execution, stage, attempt = await transitions.current(task, queue)
    status = final_run_status(body.status)
    if status in {"failed", "error", "canceled"}:
        error = body.error_message or snapshot.get("errorMessage") or ""
        if not isinstance(error, str):
            raise ErrBadRequest()
        await transitions.failed(task, queue, status=status, error_message=error)
        queue.error_message = error
        return status
    if status != "success":
        raise ErrBadRequest()
    source = execution.source_snapshot_json or {}
    names = workflow_stage_names(task.task_type, source)
    final = final_review_stage(task.task_type, names)
    supplied = _config(
        body.config_json if body.config_json is not None else snapshot.get("configJson")
    )
    reported = snapshot.get("currentStage") or snapshot.get("stage")
    if reported not in {None, stage.stage, "completed"}:
        raise ErrBadRequest()
    if stage.stage != final and stage.stage != "relation_analysis":
        if execution.checkpoint_enabled:
            raise ErrBadRequest()
        execution, stage, attempt = await _move_to(session, task, queue, final, supplied)
    frozen = _frozen(attempt)
    _check_upstream(names, stage.stage, frozen, supplied)
    if stage.stage == "relation_analysis":
        content = validate_relation_output(frozen, supplied)
        output_format = "json"
    else:
        result = (
            body.result_yaml
            or body.output_yaml
            or snapshot.get("resultYaml")
            or snapshot.get("outputYaml")
        )
        content, output_format = await _validate(session, task, stage.stage, source, result)
    context = body.result_summary_json if isinstance(body.result_summary_json, dict) else None
    await transitions.completed(
        task, queue, content=content, output_format=output_format, output_context=context
    )
    return "success"
