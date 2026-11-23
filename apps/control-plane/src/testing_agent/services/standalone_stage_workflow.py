"""Relation-analysis command for independent functional executions."""

from typing import Any

from testing_agent.core.errors import ErrBadRequest, ErrNotFound
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
    validate_function_candidate_cases,
)
from testing_agent.services.standalone_candidate import lock_standalone_candidate
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
