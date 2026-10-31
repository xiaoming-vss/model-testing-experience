"""Shared persistence helpers for UI generation chain tests; no collected tests."""

import json
from datetime import UTC, datetime
from pathlib import Path

from support.ai_execution import AsyncSessionAdapter
from testing_agent.domain.ai_execution_intent import ExecutionIntent
from testing_agent.domain.ui_generation_artifacts import UI_WORKFLOW_VERSION
from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.schemas.workers import WorkerProgressRequest
from testing_agent.services.ai_execution import persist_run
from testing_agent.services.ai_execution.writer import SqlExecutionWriter
from testing_agent.services.ai_task_scope import GenerationAccess
from testing_agent.services.ui_generation_workflow import UiGenerationWorkflow
from testing_agent.services.worker_domains.ai import apply_progress

FIXTURES = Path(__file__).parent.parent / "fixtures/ui_generation"


def read(name):
    return json.loads((FIXTURES / (name + ".json")).read_text())


def setup(db):
    db.add(
        Sprint(
            sprint_id="s",
            project_id="p",
            name="fixture",
            start_time=datetime(2026, 1, 1, tzinfo=UTC),
            end_time=datetime(2026, 2, 1, tzinfo=UTC),
        )
    )
    db.flush()
    db.add(Requirement(requirement_id="r", sprint_id="s", name="UI"))
    db.flush()
    db.add(
        AiGenerateTask(
            task_id="ui-task",
            task_type="ui_case_generate",
            name="UI",
            project_id="p",
            sprint_id="s",
            requirement_id="r",
            creator_user_id="u",
            source_type="source_archive",
            source_content="",
            instruction="",
        )
    )
    run = AiGenerateTaskRun(
        run_id="ui-run",
        task_id="ui-task",
        trigger_user_id="u",
        status="pending",
        checkpoint_enabled=True,
        current_stage="ui_surface",
        stage_status="pending",
        config_json={},
        snapshot_json={
            "uiWorkflowVersion": UI_WORKFLOW_VERSION,
            "functionalCases": read("cases"),
            "taskType": "ui_case_generate",
            "sourceArchiveDownloadUrl": "/old-dispatch/source-archive",
        },
    )
    worker = WorkerTask(
        domain="ai", task_id="w1", task_type="ui_case_generate", run_id="ui-run", status="pending"
    )
    db.add_all([run, worker])
    db.flush()
    persist_run(
        db, run, intent=ExecutionIntent(actor_id="u", llm_connection_id="llm"), worker=worker
    )
    db.commit()
    repo = AiGenerateTaskRepository(AsyncSessionAdapter(db))
    access = GenerationAccess(repo)
    flow = UiGenerationWorkflow(
        repository=repo, owned_run=access.owned_run, execution_writer=SqlExecutionWriter()
    )
    return run, worker, flow, repo


def publish(db, run, worker, stage, config):
    worker.status = "running"
    apply_progress(
        run,
        worker,
        WorkerProgressRequest(
            worker_id="worker",
            run_id=run.run_id,
            current_stage=stage,
            stage_status="waiting_review",
            config_json=config,
        ),
        lease_seconds=30,
    )
    persist_run(db, run, intent=ExecutionIntent(worker_event_id=worker.task_id), worker=worker)
    db.commit()
