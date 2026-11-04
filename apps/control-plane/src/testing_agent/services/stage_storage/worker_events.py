"""Worker event application for a direct stage attempt.

Caller must authorize, check worker identity and lease, lock the Worker queue row
first, and commit the queue and stage updates together.
"""

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.ai_tasks import task_type_for
from testing_agent.domain.generation_chain import STAGE_CONFIG_FIELDS, is_final_stage
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.schemas.workers import WorkerProgressRequest, WorkerTaskEventRequest
from testing_agent.services.generation_artifact_validation import validate_generation_artifact
from testing_agent.services.stage_storage.worker import StageWorkerTransitions
from testing_agent.services.worker_domains.events import final_run_status


def validate_relation_output(frozen: dict[str, Any], supplied: Any) -> str:
    if not isinstance(supplied, dict):
        raise ErrBadRequest()
    for name in ("requirementAnalysis", "caseNames"):
        if supplied.get(name) != frozen.get(name):
            raise ErrBadRequest()
    graph = supplied.get("caseRelations")
    try:
        cases = json.loads(frozen["resultYaml"])["cases"]
        allowed = {str(case.get("case_id") or case.get("caseId")) for case in cases}
        if not isinstance(graph, dict) or graph.get("schema_version") != "2.0":
            raise ValueError()
        paths, edges = graph["main_paths"], graph["edges"]
        if not isinstance(paths, list) or not isinstance(edges, list):
            raise ValueError()
        pairs, orders, edge_ids, next_pairs = set(), set(), set(), set()
        for edge in edges:
            start, end = edge["from_case_id"], edge["to_case_id"]
            edge_id, order, kind = edge["edge_id"], edge["order"], edge["relation_type"]
            if (
                not isinstance(edge_id, str)
                or not edge_id
                or start not in allowed
                or end not in allowed
                or start == end
                or kind not in {"next", "branch"}
                or not isinstance(order, int)
                or isinstance(order, bool)
                or order <= 0
                or edge_id in edge_ids
                or (start, end) in pairs
                or (start, order) in orders
            ):
                raise ValueError()
            edge_ids.add(edge_id)
            pairs.add((start, end))
            orders.add((start, order))
            if kind == "next":
                next_pairs.add((start, end))
        path_ids, sequences = set(), set()
        for path in paths:
            path_id, ids = path["path_id"], path["case_ids"]
            if (
                not isinstance(path_id, str)
                or not path_id
                or path_id in path_ids
                or not isinstance(ids, list)
                or len(ids) < 2
                or len(ids) != len(set(ids))
                or any(case not in allowed for case in ids)
                or tuple(ids) in sequences
                or any(pair not in next_pairs for pair in zip(ids, ids[1:], strict=False))
            ):
                raise ValueError()
            path_ids.add(path_id)
            sequences.add(tuple(ids))
    except (ValueError, KeyError, TypeError) as exc:
        raise dynamic_error(ErrBadRequest, "图谱产物无效或包含不属于该版本的用例") from exc
    return json.dumps(graph, ensure_ascii=False)


async def _artifact(
    session: AsyncSession,
    kind: DesignKind,
    stage: str,
    source: dict[str, Any],
    config: dict[str, Any],
    result: str | None,
) -> tuple[str, str]:
    if is_final_stage(kind, stage):
        content = result or ""
    else:
        field = STAGE_CONFIG_FIELDS.get(stage)
        value = config.get(field) if field else None
        content = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else ""
    return await validate_generation_artifact(
        AiGenerateTaskRepository(session), kind, stage, content, source
    )


def _check_inputs(stage: str, frozen: dict[str, Any], supplied: Any) -> dict[str, Any]:
    if supplied is None:
        return {}
    if not isinstance(supplied, dict):
        raise ErrBadRequest()
    own_field = STAGE_CONFIG_FIELDS.get(stage)
    for field in set(STAGE_CONFIG_FIELDS.values()) - {own_field}:
        if (field in supplied or field in frozen) and supplied.get(field) != frozen.get(field):
            raise ErrBadRequest()
    return supplied


async def apply_auxiliary_progress(
    session: AsyncSession,
    task: WorkerTask,
    *,
    stage_id: str,
    attempt_id: str,
    body: WorkerProgressRequest,
) -> None:
    """Validate auxiliary Worker progress without storing the detailed payload."""
    if (
        task.domain != "ai"
        or task.run_id != attempt_id
        or (body.task_id and body.task_id != task.task_id)
        or (body.run_id and body.run_id != attempt_id)
        or body.stage_status not in {None, "", "running", "failed"}
    ):
        raise ErrBadRequest()
    await StageWorkerTransitions(session).progress(stage_id, attempt_id, task.task_id, {})


async def apply_auxiliary_completion(
    session: AsyncSession,
    task: WorkerTask,
    *,
    stage_id: str,
    attempt_id: str,
    body: WorkerTaskEventRequest,
) -> None:
    """Persist a single-stage result or error under its original attempt."""
    if (
        task.domain != "ai"
        or task.run_id != attempt_id
        or (body.task_id and body.task_id != task.task_id)
        or (body.run_id and body.run_id != attempt_id)
    ):
        raise ErrBadRequest()
    transitions = StageWorkerTransitions(session)
    status = final_run_status(body.status)
    snapshot = body.snapshot_json or {}
    if status == "success":
        output = (
            body.result_yaml
            or body.output_yaml
            or snapshot.get("resultYaml")
            or snapshot.get("outputYaml")
        )
        if not isinstance(output, str):
            raise ErrBadRequest()
        await transitions.completed(
            stage_id,
            attempt_id,
            task.task_id,
            content=output,
            output_format="text",
            output_context=None,
        )
    elif status in {"failed", "error", "canceled"}:
        error = body.error_message or snapshot.get("errorMessage") or ""
        if not isinstance(error, str):
            raise ErrBadRequest()
        await transitions.failed(
            stage_id, attempt_id, task.task_id, error_message=error, status=status
        )
        task.error_message = error
    else:
        raise ErrBadRequest()
    task.status = status
    task.finished_at = datetime.now(UTC)
    task.lease_expires_at = task.finished_at


async def apply_stage_progress(
    session: AsyncSession,
    task: WorkerTask,
    *,
    stage_id: str,
    attempt_id: str,
    kind: DesignKind,
    stage: str,
    source: dict[str, Any],
    frozen_config: dict[str, Any],
    body: WorkerProgressRequest,
) -> None:
    """Apply one authorized and lease-checked progress event in the caller's transaction."""
    if (
        task.domain != "ai"
        or task.task_type != task_type_for(kind)
        or task.run_id != attempt_id
        or (body.task_id and body.task_id != task.task_id)
        or (body.run_id and body.run_id != attempt_id)
        or (body.current_stage and body.current_stage != stage)
        or (body.stage_status is not None and body.current_stage != stage)
    ):
        raise ErrBadRequest()
    supplied = _check_inputs(stage, frozen_config, body.config_json)
    transitions = StageWorkerTransitions(session)
    if body.stage_status == "waiting_review":
        if body.current_stage != stage or is_final_stage(kind, stage):
            raise ErrBadRequest()
        content, output_format = await _artifact(session, kind, stage, source, supplied, None)
        await transitions.completed(
            stage_id,
            attempt_id,
            task.task_id,
            content=content,
            output_format=output_format,
            output_context=body.result_summary_json
            if isinstance(body.result_summary_json, dict)
            else None,
        )
        task.status = "success"
        task.finished_at = datetime.now(UTC)
        task.lease_expires_at = task.finished_at
    else:
        if body.stage_status not in {None, "running"}:
            raise ErrBadRequest()
        await transitions.progress(
            stage_id,
            attempt_id,
            task.task_id,
            {"stageStatus": body.stage_status or "running", "summary": body.result_summary_json},
        )


async def apply_stage_completion(
    session: AsyncSession,
    task: WorkerTask,
    *,
    stage_id: str,
    attempt_id: str,
    kind: DesignKind,
    stage: str,
    source: dict[str, Any],
    frozen_config: dict[str, Any],
    body: WorkerTaskEventRequest,
) -> None:
    """Apply an authorized and lease-checked final result or failure atomically."""
    if (
        task.domain != "ai"
        or task.task_type != task_type_for(kind)
        or task.run_id != attempt_id
        or (body.task_id and body.task_id != task.task_id)
        or (body.run_id and body.run_id != attempt_id)
    ):
        raise ErrBadRequest()
    transitions = StageWorkerTransitions(session)
    reported = (body.snapshot_json or {}).get("currentStage") or (body.snapshot_json or {}).get(
        "stage"
    )
    if reported not in {None, stage, "completed"}:
        raise ErrBadRequest()
    status = final_run_status(body.status)
    if status == "success":
        if kind == "function" and stage == "relation_analysis":
            content = validate_relation_output(frozen_config, body.config_json)
            await transitions.completed(
                stage_id,
                attempt_id,
                task.task_id,
                content=content,
                output_format="json",
                output_context=None,
            )
            graph_stage = await transitions.storage.lock_stage(stage_id)
            graph_stage.review_status = "not_required"
        elif not is_final_stage(kind, stage):
            raise ErrBadRequest()
        else:
            supplied = _check_inputs(stage, frozen_config, body.config_json)
            content, output_format = await _artifact(
                session, kind, stage, source, supplied, body.result_yaml or body.output_yaml
            )
            await transitions.completed(
                stage_id,
                attempt_id,
                task.task_id,
                content=content,
                output_format=output_format,
                output_context=body.result_summary_json
                if isinstance(body.result_summary_json, dict)
                else None,
            )
        task.status = "success"
    elif status in {"failed", "error", "canceled"}:
        await transitions.failed(
            stage_id,
            attempt_id,
            task.task_id,
            error_message=body.error_message or "",
        )
        task.status = status
        task.error_message = body.error_message or ""
    else:
        raise ErrBadRequest()
    task.finished_at = datetime.now(UTC)
    task.lease_expires_at = task.finished_at
