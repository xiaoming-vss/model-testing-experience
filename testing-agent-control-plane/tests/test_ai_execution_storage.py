"""Real database transactions for normalized generation storage (no model calls)."""

import json

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from testing_agent.core.errors import ErrBadRequest
from testing_agent.db.base import Base
from testing_agent.models.ai_generate_execution import (
    AiGenerateRunImport as Import,
)
from testing_agent.models.ai_generate_execution import (
    AiGenerateStageAttempt as Attempt,
)
from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services.ai_execution import (
    graph,
    persist,
    project,
    require_current_worker,
    worker_input,
)


@compiles(LONGTEXT, "sqlite")
def longtext_sqlite(type_, compiler, **kw):
    return "TEXT"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        from testing_agent.models.integration_connection import IntegrationConnection
        from testing_agent.models.project import Project
        from testing_agent.models.user import User

        session.add_all(
            [
                User(user_id="u", nickname="owner"),
                Project(project_id="p", user_id="u", name="test"),
                IntegrationConnection(
                    connection_id="llm",
                    user_id="u",
                    provider="llm",
                    name="llm",
                    project_id="p",
                    status="active",
                    secret_json={"apiKey": "test"},
                ),
            ]
        )
        for key in ("fixed-model", "original-model"):
            session.add(
                IntegrationConnection(
                    connection_id=key,
                    user_id="u",
                    provider="llm",
                    name=key,
                    project_id="p",
                    status="active",
                    secret_json={"apiKey": "test"},
                )
            )
        session.commit()
        yield session
    engine.dispose()


def create_run(db, checkpoint=True):
    task = AiGenerateTask(
        task_id="task",
        task_type="functional_case_generate",
        name="test",
        project_id="p",
        sprint_id="s",
        requirement_id="r",
        creator_user_id="u",
        source_type="text",
        source_content="sample",
        instruction="",
    )
    run = AiGenerateTaskRun(
        run_id="run",
        task_id="task",
        project_id="p",
        sprint_id="s",
        requirement_id="r",
        trigger_user_id="u",
        status="pending",
        checkpoint_enabled=checkpoint,
        current_stage="requirement_analysis" if checkpoint else "",
        stage_status="pending",
        config_json={},
        snapshot_json={"sourceContent": "sample"},
    )
    db.add_all([task, run])
    db.flush()
    worker = enqueue(db, run, "w1")
    return run, worker


def enqueue(db, run, key, operation=None, *, connection_id="llm"):
    task = WorkerTask(
        domain="ai",
        task_id=key,
        task_type="functional_case_generate",
        run_id=run.run_id,
        generate_task_id=run.task_id,
        llm_connection_id=connection_id,
        status="pending",
    )
    db.add(task)
    run.status = "pending"
    if operation:
        run._operation = operation
    persist(db)
    db.commit()
    return task


def event(db, run, worker, *, status, stage, config=None, output=None):
    require_current_worker(db, run, worker)
    run._worker_event = worker.task_id
    run.current_stage = stage
    run.status = status
    run.stage_status = "waiting_review" if status == "waiting_review" else "running"
    worker.status = "success" if status in {"success", "waiting_review"} else status
    if config is not None:
        run.config_json = config
    if output is not None:
        run.result_yaml = output
    persist(db)
    db.commit()


def test_stages_and_queue_commit_together(db):
    run, worker = create_run(db)
    stages, attempts = graph(db, run)
    assert [s.stage for s in stages] == ["requirement_analysis", "case_names", "detailed_cases"]
    active = attempts[stages[0].active_attempt_id]
    assert active.worker_task_id == worker.task_id and active.operation == "generate"
    assert active.input_snapshot_json["source"] == {"sourceContent": "sample"}
    assert active.output_content is None


def test_revision_failure_keeps_effective_artifact_and_retry_input(db):
    run, first = create_run(db)
    event(
        db,
        run,
        first,
        status="waiting_review",
        stage="requirement_analysis",
        config={"requirementAnalysis": {"original": True}},
    )
    old = graph(db, run)[0][0].current_artifact_attempt_id
    run.config_json = {
        "requirementAnalysis": {"unsavedEdit": True},
        "revisionInstruction": "补充边界",
    }
    second = enqueue(db, run, "w2", "revise")
    stages, attempts = graph(db, run)
    revised = attempts[stages[0].active_attempt_id]
    assert stages[0].current_artifact_attempt_id == old
    assert revised.input_snapshot_json["config"]["requirementAnalysis"] == {"unsavedEdit": True}
    event(db, run, second, status="failed", stage="requirement_analysis")
    project(db, run)
    assert run.config_json["requirementAnalysis"] == {"original": True}
    third = enqueue(db, run, "w3", "retry")
    stages, attempts = graph(db, run)
    retried = attempts[stages[0].active_attempt_id]
    assert retried.operation == "retry"
    assert retried.input_snapshot_json == revised.input_snapshot_json
    assert retried.revision_instruction == "补充边界"
    assert "revisionInstruction" not in retried.input_snapshot_json["config"]
    assert worker_input(db, run, third)[1]["revisionInstruction"] == "补充边界"
    assert "revisionInstruction" not in retried.input_snapshot_json["config"]
    event(
        db,
        run,
        third,
        status="waiting_review",
        stage="requirement_analysis",
        config={"requirementAnalysis": {"fixed": True}},
    )
    assert graph(db, run)[0][0].current_artifact_attempt_id == retried.id
    assert graph(db, run)[1][old].output_content == json.dumps({"original": True})
    project(db, run)
    assert "revisionInstruction" not in run.config_json


def test_delayed_old_worker_cannot_overwrite_new_attempt(db):
    run, worker = create_run(db)
    event(db, run, worker, status="failed", stage="requirement_analysis")
    new = enqueue(db, run, "w2", "retry")
    with pytest.raises(type(ErrBadRequest)) as exc:
        require_current_worker(db, run, worker)
    assert "" != str(exc.value)
    require_current_worker(db, run, new)


def test_noncheckpoint_full_chain_and_atomic_final_output(db):
    run, worker = create_run(db, False)
    event(
        db,
        run,
        worker,
        status="running",
        stage="requirement_analysis",
        config={"requirementAnalysis": {"a": 1}},
    )
    event(
        db,
        run,
        worker,
        status="running",
        stage="case_names",
        config={"requirementAnalysis": {"a": 1}, "caseNames": {"categories": []}},
    )
    event(db, run, worker, status="running", stage="detailed_cases")
    stages, attempts = graph(db, run)
    assert stages[-1].current_artifact_attempt_id is None
    event(db, run, worker, status="success", stage="completed", output='{"cases":[]}')
    stages, attempts = graph(db, run)
    assert all(s.current_artifact_attempt_id for s in stages)
    assert all(s.active_attempt_id is None for s in stages)
    assert all(s.execution_status == "success" for s in stages)
    assert all(a.status == "success" for a in attempts.values())
    assert len(attempts) == 3


def test_stage_review_and_import_are_separate(db):
    run, worker = create_run(db)
    event(
        db,
        run,
        worker,
        status="waiting_review",
        stage="requirement_analysis",
        config={"requirementAnalysis": {"a": 1}},
    )
    run._actor = "reviewer"
    run._stage_review = ("requirement_analysis", "approved", "同意")
    run.current_stage = "case_names"
    worker = enqueue(db, run, "w2")
    assert graph(db, run)[0][0].reviewer_user_id == "reviewer"
    event(
        db,
        run,
        worker,
        status="waiting_review",
        stage="case_names",
        config={"requirementAnalysis": {"a": 1}, "caseNames": {"categories": []}},
    )
    run._stage_review = ("case_names", "approved", "")
    run.current_stage = "detailed_cases"
    worker = enqueue(db, run, "w3")
    event(db, run, worker, status="success", stage="completed", output='{"cases":[]}')
    assert db.scalar(select(Import)) is None
    run.review_status = "approved"
    run.reviewer_user_id = "reviewer"
    persist(db)
    db.commit()
    run.import_status = "imported"
    run.imported_targets = [{"targetType": "function_suite", "targetId": "s"}]
    run._actor = "importer"
    persist(db)
    db.commit()
    persist(db)
    db.commit()
    imports = list(db.scalars(select(Import)))
    assert len(imports) == 1
    assert imports[0].imported_by == "importer"
    assert imports[0].artifact_attempt_id == graph(db, run)[0][-1].current_artifact_attempt_id


def test_roll_back_queue_and_attempt(db):
    run, worker = create_run(db)
    event(db, run, worker, status="failed", stage="requirement_analysis")
    db.add(
        WorkerTask(
            domain="ai", task_id="w2", task_type="functional_case_generate", run_id=run.run_id
        )
    )
    run.status = "pending"
    run._operation = "retry"
    persist(db)
    db.rollback()
    assert len(list(db.scalars(select(Attempt)))) == 1
    assert len(list(db.scalars(select(WorkerTask)))) == 1


class AsyncSessionAdapter:
    """Use the real repositories/services against SQLite without an async driver."""

    def __init__(self, session):
        self.sync = session

    async def run_sync(self, fn):
        return fn(self.sync)

    async def execute(self, stmt):
        return self.sync.execute(stmt)

    async def scalar(self, stmt):
        return self.sync.scalar(stmt)

    async def scalars(self, stmt):
        return self.sync.scalars(stmt)

    async def commit(self):
        self.sync.commit()

    async def delete(self, row):
        self.sync.delete(row)

    async def flush(self):
        self.sync.flush()

    async def refresh(self, row):
        self.sync.refresh(row)

    async def rollback(self):
        self.sync.rollback()

    def add(self, row):
        self.sync.add(row)

    def add_all(self, rows):
        self.sync.add_all(rows)


@pytest.mark.asyncio
async def test_real_service_revision_progress_failure_retry_and_worker_snapshot(db):
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.repositories.worker_task import WorkerTaskRepository
    from testing_agent.schemas.workers import (
        WorkerClaimRequest,
        WorkerProgressRequest,
        WorkerTaskEventRequest,
    )
    from testing_agent.services.ai_generate_task import AiGenerateTaskService
    from testing_agent.services.worker import build_snapshot
    from testing_agent.services.worker_task import WorkerTaskService

    run, first = create_run(db)
    event(
        db,
        run,
        first,
        status="waiting_review",
        stage="requirement_analysis",
        config={"requirementAnalysis": {"original": True}},
    )
    adapter = AsyncSessionAdapter(db)
    repo = AiGenerateTaskRepository(adapter)
    service = AiGenerateTaskService(repo)
    # Actual task belongs to u, so no project lookup is necessary.
    result = await service.revise_function_case_stage(
        "run",
        {
            "stage": "requirement_analysis",
            "revisionInstruction": "补充",
            "configJson": {"requirementAnalysis": {"draft": True}},
        },
        "u",
    )
    assert result["status"] == "pending"
    task = await repo.get_latest_worker_task_by_run_id("run")
    snapshot = await build_snapshot(adapter, "ai", task)
    assert json.loads(snapshot["configJson"])["requirementAnalysis"] == {"draft": True}
    workers = WorkerTaskService(WorkerTaskRepository(adapter))
    await workers.claim("ai", WorkerClaimRequest(workerId="w"))
    await workers.started("ai", task.task_id, WorkerTaskEventRequest(workerId="w"))
    await workers.progress(
        task.task_id,
        WorkerProgressRequest(
            workerId="w",
            currentStage="requirement_analysis",
            resultSummaryJson={"outputValidation": {"status": "repairing", "repairAttempt": 1}},
            stageStatus="running",
        ),
    )
    await workers.complete(
        "ai",
        task.task_id,
        WorkerTaskEventRequest(workerId="w", status="failed", errorMessage="invalid"),
    )
    loaded = await repo.get_run("run")
    assert loaded.config_json["requirementAnalysis"] == {"original": True}
    await service.retry_stage("run", {"stage": "requirement_analysis"}, "u")
    retry = await repo.get_latest_worker_task_by_run_id("run")
    snapshot = await build_snapshot(adapter, "ai", retry)
    assert json.loads(snapshot["configJson"])["requirementAnalysis"] == {"draft": True}
    with pytest.raises(type(ErrBadRequest)):
        await workers.progress(
            task.task_id, WorkerProgressRequest(workerId="w", currentStage="requirement_analysis")
        )
    await workers.claim("ai", WorkerClaimRequest(workerId="w"))
    await workers.started("ai", retry.task_id, WorkerTaskEventRequest(workerId="w"))
    await workers.progress(
        retry.task_id,
        WorkerProgressRequest(
            workerId="w",
            currentStage="requirement_analysis",
            stageStatus="waiting_review",
            configJson={"requirementAnalysis": {"fixed": True}},
        ),
    )
    loaded = await repo.get_run("run")
    assert loaded.status == "waiting_review"
    assert loaded.config_json["requirementAnalysis"] == {"fixed": True}
    assert "revisionInstruction" not in loaded.config_json


@pytest.mark.parametrize("checkpoint", [True, False])
def test_final_revision_publishes_only_after_complete(db, checkpoint):
    run, worker = create_run(db, checkpoint)
    event(db, run, worker, status="success", stage="completed", output='{"cases":["old"]}')
    run.current_stage = "detailed_cases"
    run.result_yaml = '{"cases":["draft"]}'
    run.config_json = {"revisionInstruction": "revise", "resultYaml": run.result_yaml}
    revised = enqueue(db, run, "w2", "revise")
    assert run.result_yaml == '{"cases":["old"]}'
    event(
        db, run, revised, status="running", stage="detailed_cases", output='{"cases":["partial"]}'
    )
    assert run.result_yaml == '{"cases":["old"]}'
    event(
        db, run, revised, status="success", stage="completed", output='{"cases":["new"]}', config={}
    )
    assert run.result_yaml == '{"cases":["new"]}'
    assert "revisionInstruction" not in run.config_json
    final = graph(db, run)[0][-1]
    assert final.review_status == "pending"
    assert graph(db, run)[1][final.current_artifact_attempt_id].worker_task_id == revised.task_id


def test_projection_reads_normalized_output_not_stale_legacy_copy(db):
    run, worker = create_run(db)
    event(db, run, worker, status="success", stage="completed", output='{"cases":["valid"]}')
    run.result_yaml = "stale copy"
    db.flush()
    project(db, run)
    assert run.result_yaml == '{"cases":["valid"]}'


def test_repeated_progress_does_not_revoke_valid_upstream_output(db):
    run, worker = create_run(db, False)
    for _ in range(2):
        event(
            db,
            run,
            worker,
            status="running",
            stage="requirement_analysis",
            config={"requirementAnalysis": {"ready": True}},
        )
    stages, attempts = graph(db, run)
    assert attempts[stages[0].current_artifact_attempt_id].status == "success"
    assert stages[0].execution_status == "success"


def test_scope_comes_from_task_and_report_needs_no_requirement(db):
    run, _ = create_run(db)
    task = db.scalar(select(AiGenerateTask).where(AiGenerateTask.task_id == run.task_id))
    from testing_agent.models.project import Project

    db.add(Project(project_id="new-project", user_id="u", name="new"))
    db.flush()
    task.project_id = "new-project"
    task.sprint_id = "new-sprint"
    task.requirement_id = ""
    db.flush()
    project(db, run)
    assert (run.project_id, run.sprint_id, run.requirement_id) == ("new-project", "new-sprint", "")
    assert "created_at" in AiGenerateTaskRun.__table__.columns
    assert len(AiGenerateTaskRun.__table__.columns) == 11


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stage,field,content_key",
    [
        ("requirement_analysis", "requirementAnalysis", "functionalOverview"),
        ("case_names", "caseNames", "categories"),
    ],
)
@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("as_string", [False, True])
async def test_stage_save_replaces_artifact_after_reload(
    db, stage, field, content_key, wrapped, as_string
):
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.services.ai_generate_task import AiGenerateTaskService

    run, worker = create_run(db)
    event(
        db,
        run,
        worker,
        status="waiting_review",
        stage=stage,
        config={field: {content_key: [{"name": "old"}], "removed": True}},
    )
    service = AiGenerateTaskService(AiGenerateTaskRepository(AsyncSessionAdapter(db)))
    edited = {content_key: [{"name": "edited"}]}
    config = {field: edited} if wrapped else edited
    result = await service.save_stage_output(
        "run",
        {
            "stage": stage,
            "configJson": json.dumps(config) if as_string else config,
        },
        "u",
    )
    assert result["configJson"][field] == edited
    db.expire_all()
    reloaded = await service.owned_run("u", "run", "function")
    assert reloaded.config_json[field] == edited
    assert reloaded.status == "waiting_review"
    continued = await service.review_stage("run", {"stage": stage, "action": "approve"}, "u")
    assert continued["status"] == "pending"
    assert (
        continued["currentStage"]
        == {"requirement_analysis": "case_names", "case_names": "detailed_cases"}[stage]
    )
    assert continued["configJson"][field] == edited


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "review,import_status",
    [("approved", "pending"), ("rejected", "pending"), ("approved", "imported")],
)
async def test_stage_save_cannot_change_frozen_result_in_database(db, review, import_status):
    from testing_agent.core.errors import AppError
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
    from testing_agent.services.ai_generate_task import AiGenerateTaskService

    run, worker = create_run(db)
    event(db, run, worker, status="success", stage="completed", output='{"cases": []}')
    run.review_status = review
    run.import_status = import_status
    persist(db)
    db.commit()
    service = AiGenerateTaskService(AiGenerateTaskRepository(AsyncSessionAdapter(db)))
    before = await service.owned_run("u", "run", "function")
    expected = (
        before.result_yaml,
        before.review_status,
        before.import_status,
        before.current_stage,
    )
    with pytest.raises(AppError):
        await service.save_stage_output(
            "run", {"stage": "completed", "resultYaml": "unreviewed replacement"}, "u"
        )
    db.expire_all()
    after = await service.owned_run("u", "run", "function")
    assert (
        after.result_yaml,
        after.review_status,
        after.import_status,
        after.current_stage,
    ) == expected
