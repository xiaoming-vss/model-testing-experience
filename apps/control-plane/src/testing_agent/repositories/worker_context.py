"""Read owning execution identities without changing a queue ORM object."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from testing_agent.core.errors import ErrBadRequest
from testing_agent.domain.worker_context import (
    AiWorkerContext,
    ApiWorkerContext,
    PerfWorkerContext,
    UiWorkerContext,
    WorkerExecutionContext,
)
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.api_collection_run import ApiCollectionRun
from testing_agent.models.perf_run import PerfRun
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
            row = session.execute(
                select(ApiCollectionRun.collection_id, ApiCollectionRun.collection_run_id).where(
                    ApiCollectionRun.collection_run_id == task.run_id
                )
            ).one_or_none()
            return ApiWorkerContext(
                None,
                row.collection_id if row else None,
                row.collection_run_id if row else None,
            )
        row = session.execute(
            select(
                ApiCaseRun.case_id, ApiCaseRun.collection_id, ApiCaseRun.collection_run_id
            ).where(ApiCaseRun.run_id == task.run_id)
        ).one_or_none()
        return ApiWorkerContext(
            row.case_id if row else None,
            row.collection_id if row else None,
            row.collection_run_id if row else None,
        )
    if task.domain == "perf":
        case_id = session.scalar(select(PerfRun.case_id).where(PerfRun.run_id == task.run_id))
        return PerfWorkerContext(case_id)
    if task.domain == "ui":
        if task.task_type == "suite_run":
            suite_id = session.scalar(
                select(UiTestSuiteRun.suite_id).where(UiTestSuiteRun.suite_run_id == task.run_id)
            )
            return UiWorkerContext(None, suite_id)
        row = session.execute(
            select(UiTestCaseRun.case_id, UiTestCaseRun.suite_id).where(
                UiTestCaseRun.run_id == task.run_id
            )
        ).one_or_none()
        return UiWorkerContext(
            row.case_id if row else None,
            row.suite_id if row else None,
        )
    raise ErrBadRequest()
