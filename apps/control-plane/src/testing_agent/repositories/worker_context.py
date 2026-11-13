"""Read owning execution identities without changing a queue ORM object."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from testing_agent.core.errors import ErrBadRequest
from testing_agent.domain.worker_context import (
    AiWorkerContext,
    ApiWorkerContext,
    UiWorkerContext,
    WorkerExecutionContext,
)
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
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
        row = session.execute(
            select(AiGenerationStage.task_id, AiGenerationAttempt.input_snapshot_json)
            .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
            .where(
                AiGenerationAttempt.id == task.run_id,
                AiGenerationAttempt.worker_task_id == task.task_id,
            )
        ).one_or_none()
        if row is None:
            return AiWorkerContext(None, None)
        return AiWorkerContext(row.task_id, (row.input_snapshot_json or {}).get("llmConnectionId"))
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
