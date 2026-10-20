"""Read owning execution identities without changing a queue ORM object."""

from typing import overload

from sqlalchemy import select
from sqlalchemy.orm import Session

from testing_agent.core.errors import ErrBadRequest
from testing_agent.domain.worker_context import (
    AiWorkerContext,
    ApiWorkerContext,
    UiWorkerContext,
    WorkerExecutionContext,
)
from testing_agent.models.ai_generate_execution import AiGenerateRunStage, AiGenerateStageAttempt
from testing_agent.models.ai_generate_task import AiGenerateTaskRun
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.api_collection_run import ApiCollectionRun
from testing_agent.models.ui_test_case_run import UiTestCaseRun
from testing_agent.models.ui_test_suite_run import UiTestSuiteRun
from testing_agent.models.worker_task import WorkerTask


def read_worker_context(session: Session, task: WorkerTask) -> WorkerExecutionContext:
    """Resolve only the dispatch's owning run and frozen attempt.

    Missing owners produce empty identities, preserving existing not-found and
    authorization handling at the business entry point. A caller must not use
    this read result as authorization or as a replacement for locking the queue.
    """
    if task.domain == "ai":
        generate_task_id = session.scalar(
            select(AiGenerateTaskRun.task_id).where(AiGenerateTaskRun.run_id == task.run_id)
        )
        attempt = session.scalar(
            select(AiGenerateStageAttempt)
            .join(AiGenerateRunStage, AiGenerateRunStage.id == AiGenerateStageAttempt.stage_id)
            .where(
                AiGenerateRunStage.run_id == task.run_id,
                AiGenerateStageAttempt.worker_task_id == task.task_id,
            )
            .order_by(AiGenerateStageAttempt.attempt_no.desc())
        )
        connection_id = (
            (attempt.input_snapshot_json or {}).get("llmConnectionId") if attempt else None
        )
        return AiWorkerContext(generate_task_id, connection_id)
    if task.domain == "api":
        if task.task_type == "api_collection_run":
            collection_run = session.scalar(
                select(ApiCollectionRun).where(ApiCollectionRun.collection_run_id == task.run_id)
            )
            return ApiWorkerContext(
                None,
                collection_run.collection_id if collection_run else None,
                collection_run.collection_run_id if collection_run else None,
            )
        case_run = session.scalar(select(ApiCaseRun).where(ApiCaseRun.run_id == task.run_id))
        return ApiWorkerContext(
            case_run.case_id if case_run else None,
            case_run.collection_id if case_run else None,
            case_run.collection_run_id if case_run else None,
        )
    if task.domain == "ui":
        if task.task_type == "suite_run":
            suite_run = session.scalar(
                select(UiTestSuiteRun).where(UiTestSuiteRun.suite_run_id == task.run_id)
            )
            return UiWorkerContext(None, suite_run.suite_id if suite_run else None)
        ui_case_run = session.scalar(
            select(UiTestCaseRun).where(UiTestCaseRun.run_id == task.run_id)
        )
        return UiWorkerContext(
            ui_case_run.case_id if ui_case_run else None,
            ui_case_run.suite_id if ui_case_run else None,
        )
    raise ErrBadRequest()


@overload
def project_worker_context(session: Session, task: None) -> None: ...


@overload
def project_worker_context(session: Session, task: WorkerTask) -> WorkerTask: ...


def project_worker_context(session: Session, task: WorkerTask | None) -> WorkerTask | None:
    """Temporary legacy projection while callers migrate to explicit contexts.

    This is the only compatibility writer for the six nonpersistent identity
    fields. Context queries themselves never mutate the queue.
    """
    if task is None:
        return None
    values: dict[str, str | None] = dict.fromkeys(
        (
            "suite_id",
            "case_id",
            "collection_id",
            "collection_run_id",
            "generate_task_id",
            "llm_connection_id",
        )
    )
    # Queue locking tests use a synthetic domain with no owning execution.
    # Domain validation belongs to execution entry points, not queue mechanics.
    if task.domain in {"ai", "api", "ui"}:
        context = read_worker_context(session, task)
        if isinstance(context, AiWorkerContext):
            values["generate_task_id"] = context.generate_task_id
            values["llm_connection_id"] = context.llm_connection_id
        elif isinstance(context, ApiWorkerContext):
            values["case_id"] = context.case_id
            values["collection_id"] = context.collection_id
            values["collection_run_id"] = context.collection_run_id
        else:
            values["case_id"] = context.case_id
            values["suite_id"] = context.suite_id
    for name, value in values.items():
        setattr(task, name, value)
    return task


def connection_for_attempt(session: Session, worker: WorkerTask | None) -> str | None:
    """Preserve a newly selected connection before its first attempt is written."""
    if worker is None:
        return None
    if worker.llm_connection_id is not None:
        return worker.llm_connection_id
    context = read_worker_context(session, worker)
    return context.llm_connection_id if isinstance(context, AiWorkerContext) else None
