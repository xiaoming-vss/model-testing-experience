"""Rebuild legacy worker payload fields from the owning execution."""

from sqlalchemy import select

from testing_agent.models.ai_generate_execution import AiGenerateRunStage, AiGenerateStageAttempt
from testing_agent.models.ai_generate_task import AiGenerateTaskRun
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.api_collection_run import ApiCollectionRun
from testing_agent.models.ui_test_case_run import UiTestCaseRun
from testing_agent.models.ui_test_suite_run import UiTestSuiteRun


def hydrate(session, task):
    if task is None:
        return None
    for name in (
        "suite_id",
        "case_id",
        "collection_id",
        "collection_run_id",
        "generate_task_id",
        "llm_connection_id",
    ):
        setattr(task, name, None)
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
        task.generate_task_id = generate_task_id
        if attempt:
            task.llm_connection_id = (attempt.input_snapshot_json or {}).get("llmConnectionId")
    else:
        if task.domain == "api":
            model, key = (
                (ApiCollectionRun, "collection_run_id")
                if (task.task_type == "api_collection_run")
                else (ApiCaseRun, "run_id")
            )
        else:
            model, key = (
                (UiTestSuiteRun, "suite_run_id")
                if (task.task_type == "suite_run")
                else (UiTestCaseRun, "run_id")
            )
        run = session.scalar(select(model).where(getattr(model, key) == task.run_id))
        if run:
            for name in ("suite_id", "case_id", "collection_id", "collection_run_id"):
                setattr(task, name, getattr(run, name, None))
    return task


def connection_for_attempt(session, worker):
    if worker is None:
        return None
    if worker.llm_connection_id is not None:
        return worker.llm_connection_id
    return hydrate(session, worker).llm_connection_id
