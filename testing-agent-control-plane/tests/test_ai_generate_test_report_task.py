from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from authorization_database import AuthorizationDatabase
from fastapi.testclient import TestClient

from testing_agent.api.deps import get_ai_generate_task_service, get_current_user_id
from testing_agent.app import create_app
from testing_agent.core.errors import ErrBadRequest
from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
from testing_agent.models.worker_task import WorkerTask
from testing_agent.services import ai_generate_task as ai_tasks


class FakeDailyMetricsService:
    def __init__(self):
        self.calls: list[tuple[str, str, str]] = []

    async def get(self, sprint_id: str, snapshot_date: str, user_id: str) -> dict:
        self.calls.append((sprint_id, snapshot_date, user_id))
        return {
            "projectId": "project-1",
            "sprintId": sprint_id,
            "snapshotDate": snapshot_date,
            "function": {"total": 10, "executed": 8},
            "createdAt": datetime(2026, 7, 28, 9, 30, tzinfo=UTC),
            "updatedAt": datetime(2026, 7, 28, 10, 30, tzinfo=UTC),
        }


class FakeRepository:
    session = AuthorizationDatabase()

    def __init__(self):
        self.added_batches: list[list[object]] = []
        self.existing_task = None
        self.task = None
        self.run = None
        self.runs: list[AiGenerateTaskRun] = []
        self.active_task_queries: list[tuple[str, str, str]] = []
        self.list_run_queries: list[tuple[str, str, str]] = []

    async def get_project(self, project_id: str):
        return SimpleNamespace(project_id=project_id, user_id="user-1")

    async def get_sprint(self, sprint_id: str):
        return SimpleNamespace(sprint_id=sprint_id, project_id="project-1", name="Sprint 1")

    async def get_active_task_by_project_sprint_type(
        self, project_id: str, sprint_id: str, task_type: str
    ):
        self.active_task_queries.append((project_id, sprint_id, task_type))
        return self.existing_task

    async def list_runs_by_project_sprint_task_type(
        self, project_id: str, sprint_id: str, task_type: str
    ):
        self.list_run_queries.append((project_id, sprint_id, task_type))
        return self.runs

    async def get_task(self, task_id: str):
        return self.task

    async def get_run(self, run_id: str):
        return self.run

    def add_all(self, rows: list[object]) -> None:
        self.added_batches.append(rows)

    async def commit(self) -> None:
        return None

    async def refresh(self, row: object) -> None:
        if isinstance(row, AiGenerateTaskRun):
            row.error_message = row.error_message or ""
            row.result_yaml = row.result_yaml or ""
            row.review_status = row.review_status or "pending"
            row.reviewer_user_id = row.reviewer_user_id or ""
            row.reviewed_at = row.reviewed_at or None
            row.review_comment = row.review_comment or ""
            row.duration_ms = row.duration_ms or 0


def existing_test_report_task() -> AiGenerateTask:
    task = AiGenerateTask(
        task_id="task-1",
        task_type="test_report_generate",
        name="Sprint 1 report",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="",
        creator_user_id="user-1",
        source_type="daily_metrics",
        source_content="",
        instruction="",
    )
    task.id = 1
    return task


def completed_test_report_run(
    result_yaml: str = "# 测试报告\n\n- 通过率：95%",
) -> AiGenerateTaskRun:
    return AiGenerateTaskRun(
        run_id="run-1",
        task_id="task-1",
        requirement_id="",
        sprint_id="sprint-1",
        project_id="project-1",
        trigger_user_id="user-1",
        trigger_type="manual",
        status="success",
        checkpoint_enabled=False,
        current_stage="",
        stage_status="",
        snapshot_json={"name": "Sprint 1 测试报告"},
        error_message="",
        config_json={},
        result_yaml=result_yaml,
        result_summary_json={},
        review_status="pending",
        reviewer_user_id="",
        reviewed_at=None,
        review_comment="",
        duration_ms=12,
    )


@pytest.mark.asyncio
async def test_test_report_direct_run_lazily_creates_internal_task(monkeypatch):
    ids = iter(["task-1", "run-1", "worker-task-1"])
    monkeypatch.setattr(ai_tasks, "new_id", lambda: next(ids))
    repository = FakeRepository()
    daily_metrics = FakeDailyMetricsService()
    service = ai_tasks.AiGenerateTaskService(repository, daily_metrics)

    payload = await service.run_test_report(
        "project-1",
        {
            "sprintId": "sprint-1",
            "connectionId": "llm-1",
            "snapshotDate": "2026-07-27",
            "instruction": "write concise report",
        },
        "user-1",
    )

    assert repository.active_task_queries == [("project-1", "sprint-1", "test_report_generate")]
    assert daily_metrics.calls == [("sprint-1", "2026-07-27", "user-1")]
    assert len(repository.added_batches) == 1
    task, run, worker_task = repository.added_batches[0]
    assert isinstance(task, AiGenerateTask)
    assert task.task_id == "task-1"
    assert task.task_type == "test_report_generate"
    assert task.project_id == "project-1"
    assert task.sprint_id == "sprint-1"
    assert run.run_id == "run-1"
    assert run.task_id == "task-1"
    assert run.snapshot_json["snapshotDate"] == "2026-07-27"
    assert run.snapshot_json["llmConnectionId"] == "llm-1"
    assert run.snapshot_json["dailyMetrics"]["function"]["total"] == 10
    assert run.snapshot_json["dailyMetrics"]["createdAt"] == "2026-07-28T09:30:00+00:00"
    assert run.snapshot_json["dailyMetrics"]["updatedAt"] == "2026-07-28T10:30:00+00:00"
    assert run.snapshot_json["instruction"] == "write concise report"
    assert isinstance(worker_task, WorkerTask)
    assert worker_task.task_id == "worker-task-1"
    assert worker_task.domain == "ai"
    assert worker_task.task_type == "test_report_generate"
    assert worker_task.generate_task_id == "task-1"
    assert worker_task.llm_connection_id == "llm-1"
    assert payload["snapshotJson"] == run.snapshot_json


@pytest.mark.asyncio
async def test_test_report_direct_run_reuses_existing_internal_task(monkeypatch):
    ids = iter(["run-1", "worker-task-1"])
    monkeypatch.setattr(ai_tasks, "new_id", lambda: next(ids))
    repository = FakeRepository()
    repository.existing_task = existing_test_report_task()
    service = ai_tasks.AiGenerateTaskService(repository, FakeDailyMetricsService())

    await service.run_test_report(
        "project-1",
        {"sprintId": "sprint-1", "llmConnectionId": "llm-1", "snapshotDate": "2026-07-27"},
        "user-1",
    )

    assert len(repository.added_batches) == 1
    assert [type(row) for row in repository.added_batches[0]] == [
        AiGenerateTaskRun,
        WorkerTask,
    ]
    run, worker_task = repository.added_batches[0]
    assert run.task_id == "task-1"
    assert worker_task.generate_task_id == "task-1"


@pytest.mark.asyncio
async def test_test_report_allows_repeated_runs_for_same_snapshot_date(monkeypatch):
    ids = iter(["run-1", "worker-task-1", "run-2", "worker-task-2"])
    monkeypatch.setattr(ai_tasks, "new_id", lambda: next(ids))
    repository = FakeRepository()
    repository.existing_task = existing_test_report_task()
    service = ai_tasks.AiGenerateTaskService(repository, FakeDailyMetricsService())

    for _ in range(2):
        await service.run_test_report(
            "project-1",
            {"sprintId": "sprint-1", "connectionId": "llm-1", "snapshotDate": "2026-07-27"},
            "user-1",
        )

    assert [rows[0].run_id for rows in repository.added_batches] == ["run-1", "run-2"]
    assert [rows[1].task_id for rows in repository.added_batches] == [
        "worker-task-1",
        "worker-task-2",
    ]


@pytest.mark.asyncio
async def test_test_report_run_requires_snapshot_date_and_connection_id():
    service = ai_tasks.AiGenerateTaskService(FakeRepository(), FakeDailyMetricsService())

    with pytest.raises(type(ErrBadRequest)):
        await service.run_test_report("project-1", {"sprintId": "sprint-1"}, "user-1")


@pytest.mark.asyncio
async def test_list_test_report_runs_filters_by_project_sprint_and_task_type():
    repository = FakeRepository()
    repository.runs = [
        AiGenerateTaskRun(
            run_id="run-2",
            task_id="task-1",
            requirement_id="",
            sprint_id="sprint-1",
            project_id="project-1",
            trigger_user_id="user-1",
            trigger_type="manual",
            status="succeeded",
            checkpoint_enabled=False,
            current_stage="",
            stage_status="",
            snapshot_json={"snapshotDate": "2026-07-27"},
            error_message="",
            config_json={},
            result_yaml="report",
            result_summary_json={},
            review_status="pending",
            reviewer_user_id="",
            reviewed_at=None,
            review_comment="",
            duration_ms=12,
        )
    ]
    service = ai_tasks.AiGenerateTaskService(repository, FakeDailyMetricsService())

    payload = await service.list_test_report_runs("project-1", "sprint-1", "user-1")

    assert repository.list_run_queries == [("project-1", "sprint-1", "test_report_generate")]
    assert payload["total"] == 1
    assert payload["items"][0]["runId"] == "run-2"


@pytest.mark.asyncio
async def test_export_test_report_pdf_renders_markdown_bytes():
    repository = FakeRepository()
    repository.task = existing_test_report_task()
    repository.run = completed_test_report_run()
    service = ai_tasks.AiGenerateTaskService(repository, FakeDailyMetricsService())

    content, filename = await service.export_test_report_pdf("run-1", "user-1")

    assert filename == "test-report-run-1.pdf"
    assert content.startswith(b"%PDF")
    assert len(content) > 1000


@pytest.mark.asyncio
async def test_export_test_report_pdf_requires_generated_markdown():
    repository = FakeRepository()
    repository.task = existing_test_report_task()
    repository.run = completed_test_report_run(result_yaml="")
    service = ai_tasks.AiGenerateTaskService(repository, FakeDailyMetricsService())

    with pytest.raises(type(ErrBadRequest)):
        await service.export_test_report_pdf("run-1", "user-1")


def test_export_test_report_pdf_endpoint_returns_file_response():
    class FakeAiGenerateTaskService:
        async def export_test_report_pdf(self, run_id: str, user_id: str):
            assert run_id == "run-1"
            assert user_id == "user-1"
            return b"%PDF-1.4\nfake", "test-report-run-1.pdf"

    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_ai_generate_task_service] = lambda: FakeAiGenerateTaskService()
    client = TestClient(app)

    response = client.get("/v1/test-report-generate-runs/run-1/pdf")

    assert response.status_code == 200
    assert response.content == b"%PDF-1.4\nfake"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        'attachment; filename="test-report-run-1.pdf"'
    )
