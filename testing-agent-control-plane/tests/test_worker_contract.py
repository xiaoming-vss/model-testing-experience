from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from testing_agent.api.deps import get_worker_task_service
from testing_agent.app import create_app
from testing_agent.core.config import Settings, get_settings
from testing_agent.schemas.workers import (
    WorkerClaimRequest,
    WorkerProgressRequest,
    WorkerTaskEventRequest,
)
from testing_agent.services import worker as worker_service_module
from testing_agent.services import worker_task as worker_task_service_module
from testing_agent.services.worker_task import WorkerTaskService


class FakeWorkerRepository:
    def __init__(self, task=None):
        self.session = SimpleNamespace()
        self.task = task

    async def claim_pending(self, domain: str):
        return self.task if domain == "ui" else None

    async def commit(self):
        return None

    async def refresh(self, row):
        return None


def worker_settings() -> Settings:
    return Settings(
        env="test",
        http_host="127.0.0.1",
        http_port=8000,
        jwt_key="test-jwt",
        jwt_expire_hours=1,
        integration_key="test-integration",
        worker_key="worker-token",
        database_url="sqlite+aiosqlite:///:memory:",
        uploads_dir="storage/test-uploads",
    )


@pytest.mark.asyncio
async def test_worker_claim_service_returns_go_style_task_payload(monkeypatch):
    task = SimpleNamespace(
        task_id="task-1",
        task_type="case_debug",
        domain="ui",
        run_id="run-1",
        suite_id="suite-1",
        case_id="case-1",
        collection_run_id="",
        collection_id="",
        generate_task_id="",
        status="pending",
        worker_id="",
        started_at=None,
        heartbeat_at=None,
        lease_expires_at=None,
    )

    async def fake_snapshot(session, domain, claimed_task):
        return {
            "taskId": claimed_task.task_id,
            "taskType": claimed_task.task_type,
            "runId": claimed_task.run_id,
        }

    monkeypatch.setattr(worker_task_service_module, "build_snapshot", fake_snapshot)

    service = WorkerTaskService(FakeWorkerRepository(task))

    payload = await service.claim("ui", WorkerClaimRequest(workerId="worker-1"))

    assert payload["taskId"] == "task-1"
    assert payload["runId"] == "run-1"
    assert "task" not in payload


def test_internal_ui_worker_claim_returns_direct_task_payload():
    class FakeWorkerService:
        async def claim(self, domain, body):
            assert domain == "ui"
            assert body.worker_id == "worker-1"
            return {
                "taskId": "task-1",
                "taskType": "case_debug",
                "runId": "run-1",
                "caseId": "case-1",
            }

    app = create_app(worker_settings())
    app.dependency_overrides[get_worker_task_service] = lambda: FakeWorkerService()
    app.dependency_overrides[get_settings] = worker_settings
    client = TestClient(app)

    response = client.post(
        "/internal/ui-worker/tasks/claim",
        headers={"X-Worker-Token": "worker-token"},
        json={"workerId": "worker-1"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "taskId": "task-1",
        "taskType": "case_debug",
        "runId": "run-1",
        "caseId": "case-1",
    }


def test_internal_ui_worker_claim_returns_204_when_no_task():
    class FakeWorkerService:
        async def claim(self, domain, body):
            return None

    app = create_app(worker_settings())
    app.dependency_overrides[get_worker_task_service] = lambda: FakeWorkerService()
    app.dependency_overrides[get_settings] = worker_settings
    client = TestClient(app)

    response = client.post(
        "/internal/ui-worker/tasks/claim",
        headers={"X-Worker-Token": "worker-token"},
        json={"workerId": "worker-1"},
    )

    assert response.status_code == 204
    assert not response.content


def test_internal_api_worker_completed_accepts_go_runtime_vars_json_string():
    class FakeWorkerService:
        async def complete(self, domain, task_id, body):
            assert domain == "api"
            assert task_id == "task-1"
            assert body.worker_id == "worker-1"
            assert body.runtime_vars_json == {"token": "abc"}
            return {"taskId": task_id, "workerId": body.worker_id, "status": body.status}

    app = create_app(worker_settings())
    app.dependency_overrides[get_worker_task_service] = lambda: FakeWorkerService()
    app.dependency_overrides[get_settings] = worker_settings
    client = TestClient(app)

    response = client.post(
        "/internal/api-worker/tasks/task-1/completed",
        headers={"X-Worker-Token": "worker-token"},
        json={
            "workerId": "worker-1",
            "taskId": "task-1",
            "runId": "run-1",
            "caseId": "case-1",
            "status": "success",
            "success": True,
            "startedAt": "2026-06-26T14:44:00Z",
            "finishedAt": "2026-06-26T14:44:01Z",
            "durationMs": 1000,
            "runtimeVarsJson": '{"token":"abc"}',
            "extractResults": [],
            "assertResults": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "taskId": "task-1",
        "workerId": "worker-1",
        "status": "success",
    }


def test_internal_ai_worker_progress_accepts_go_string_payload_fields():
    class FakeWorkerService:
        async def progress(self, task_id, body):
            assert task_id == "task-1"
            assert body.worker_id == "worker-1"
            assert body.task_id == "task-1"
            assert body.run_id == "run-1"
            assert body.current_stage == "requirement_analysis"
            assert body.stage_status == "running"
            assert body.config_json == "plain config snapshot"
            assert body.result_yaml == "cases: []"
            assert body.result_summary_json == "summary text"
            return {"taskId": task_id}

    app = create_app(worker_settings())
    app.dependency_overrides[get_worker_task_service] = lambda: FakeWorkerService()
    app.dependency_overrides[get_settings] = worker_settings
    client = TestClient(app)

    response = client.patch(
        "/internal/ai-worker/tasks/task-1/progress",
        headers={"X-Worker-Token": "worker-token"},
        json={
            "workerId": "worker-1",
            "taskId": "task-1",
            "runId": "run-1",
            "currentStage": "requirement_analysis",
            "stageStatus": "running",
            "configJson": "plain config snapshot",
            "resultYaml": "cases: []",
            "resultSummaryJson": "summary text",
        },
    )

    assert response.status_code == 204
    assert not response.content


def test_internal_ai_worker_completed_accepts_go_string_payload_fields():
    class FakeWorkerService:
        async def complete(self, domain, task_id, body):
            assert domain == "ai"
            assert task_id == "task-1"
            assert body.worker_id == "worker-1"
            assert body.config_json == "plain config snapshot"
            assert body.result_yaml == "cases: []"
            assert body.result_summary_json == "summary text"
            return {"taskId": task_id, "workerId": body.worker_id, "status": body.status}

    app = create_app(worker_settings())
    app.dependency_overrides[get_worker_task_service] = lambda: FakeWorkerService()
    app.dependency_overrides[get_settings] = worker_settings
    client = TestClient(app)

    response = client.post(
        "/internal/ai-worker/tasks/task-1/completed",
        headers={"X-Worker-Token": "worker-token"},
        json={
            "workerId": "worker-1",
            "taskId": "task-1",
            "runId": "run-1",
            "status": "success",
            "startedAt": "2026-06-28T14:08:00Z",
            "finishedAt": "2026-06-28T14:08:05Z",
            "configJson": "plain config snapshot",
            "resultYaml": "cases: []",
            "resultSummaryJson": "summary text",
        },
    )

    assert response.status_code == 204
    assert not response.content


def test_internal_ai_worker_requirement_document_download_uses_worker_token():
    class FakeWorkerService:
        async def requirement_document(self, task_id):
            assert task_id == "worker-task-1"
            return SimpleNamespace(
                document_storage_path="",
                document_filename="requirement.docx",
                content=b"docx-bytes",
            )

    app = create_app(worker_settings())
    app.dependency_overrides[get_worker_task_service] = lambda: FakeWorkerService()
    app.dependency_overrides[get_settings] = worker_settings
    client = TestClient(app)

    unauthorized = client.get("/internal/ai-worker/tasks/worker-task-1/requirement-document")
    response = client.get(
        "/internal/ai-worker/tasks/worker-task-1/requirement-document",
        headers={"X-Worker-Token": "worker-token"},
    )

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert response.content == b"docx-bytes"
    assert response.headers["content-type"] == "application/octet-stream"


@pytest.mark.asyncio
async def test_functional_case_worker_can_download_requirement_document(monkeypatch):
    class FakeRepository:
        session = object()

        async def get_ai_run(self, run_id):
            assert run_id == "run-1"
            return SimpleNamespace(run_id="run-1", requirement_id="requirement-1")

        async def get_requirement(self, requirement_id):
            assert requirement_id == "requirement-1"
            return SimpleNamespace(
                document_storage_path="storage/requirements/requirement-1/requirement.docx"
            )

    async def fake_find_task(session, domain, task_id):
        assert domain == "ai"
        assert task_id == "worker-task-1"
        return SimpleNamespace(
            task_id="worker-task-1",
            task_type="functional_case_generate",
            run_id="run-1",
        )

    monkeypatch.setattr(worker_task_service_module, "find_task", fake_find_task)

    requirement = await WorkerTaskService(FakeRepository()).requirement_document("worker-task-1")

    assert requirement.document_storage_path.endswith("requirement.docx")


@pytest.mark.asyncio
async def test_ai_worker_claim_returns_go_style_generation_fields():
    task = SimpleNamespace(
        task_id="worker-task-1",
        task_type="api_case_generate",
        domain="ai",
        run_id="run-1",
        suite_id="",
        case_id="",
        collection_run_id="",
        collection_id="",
        generate_task_id="generate-task-1",
        llm_connection_id="llm-1",
        status="pending",
        worker_id="",
        heartbeat_at=None,
        lease_expires_at=None,
    )
    run = SimpleNamespace(
        run_id="run-1",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="requirement-1",
        checkpoint_enabled=False,
        current_stage="queued",
        stage_status="pending",
        status="pending",
    )

    class FakeAiWorkerRepository(FakeWorkerRepository):
        async def claim_pending(self, domain: str):
            return task if domain == "ai" else None

        async def get_ai_run(self, run_id: str):
            assert run_id == "run-1"
            return run

    service = WorkerTaskService(FakeAiWorkerRepository(task))

    payload = await service.claim("ai", WorkerClaimRequest(workerId="worker-1"))

    assert payload == {
        "taskId": "worker-task-1",
        "taskType": "api_case_generate",
        "runId": "run-1",
        "generateTaskId": "generate-task-1",
        "projectId": "project-1",
        "sprintId": "sprint-1",
        "requirementId": "requirement-1",
        "llmConnectionId": "llm-1",
        "checkpointEnabled": False,
        "currentStage": "queued",
        "leaseSeconds": 30,
    }
    assert run.status == "claimed"


@pytest.mark.asyncio
async def test_ai_worker_started_updates_run_status_to_running(monkeypatch):
    task = SimpleNamespace(
        task_id="worker-task-1",
        domain="ai",
        run_id="run-1",
        status="claimed",
        worker_id="worker-1",
        heartbeat_at=None,
        lease_expires_at=None,
        started_at=None,
        finished_at=None,
        error_message="",
    )
    run = SimpleNamespace(
        run_id="run-1",
        status="claimed",
        checkpoint_enabled=True,
        stage_status="pending",
        started_at=None,
    )

    class FakeAiWorkerRepository(FakeWorkerRepository):
        async def get_ai_run(self, run_id: str):
            assert run_id == "run-1"
            return run

    async def fake_find_task(session, domain, task_id):
        assert domain == "ai"
        assert task_id == "worker-task-1"
        return task

    monkeypatch.setattr(worker_task_service_module, "find_task", fake_find_task)
    service = WorkerTaskService(FakeAiWorkerRepository(task))

    await service.started(
        "ai",
        "worker-task-1",
        WorkerTaskEventRequest(
            workerId="worker-1",
            startedAt="2026-06-28T14:08:00Z",
        ),
    )

    assert task.status == "running"
    assert run.status == "running"
    assert run.stage_status == "running"
    assert run.started_at is not None


@pytest.mark.asyncio
async def test_ai_worker_snapshot_returns_go_style_run_payload():
    task = SimpleNamespace(
        task_id="worker-task-1",
        task_type="functional_case_generate",
        domain="ai",
        run_id="run-1",
        generate_task_id="generate-task-1",
    )
    run = SimpleNamespace(
        run_id="run-1",
        checkpoint_enabled=True,
        current_stage="requirement_analysis",
        config_json={"temperature": 0.2},
        snapshot_json={
            "taskId": "generate-task-1",
            "runId": "run-1",
            "taskType": "functional_case_generate",
            "name": "Generate function cases",
            "projectId": "project-1",
            "sprintId": "sprint-1",
            "requirementId": "requirement-1",
            "sourceType": "text",
            "sourceContent": "requirement doc",
            "instruction": "cover edge cases",
        },
    )

    class FakeSession:
        async def scalar(self, statement):
            return run

    payload = await worker_service_module.build_snapshot(FakeSession(), "ai", task)

    assert payload == {
        "taskType": "functional_case_generate",
        "checkpointEnabled": True,
        "currentStage": "requirement_analysis",
        "configJson": '{"temperature":0.2}',
        "run": {
            "taskId": "generate-task-1",
            "runId": "run-1",
            "taskType": "functional_case_generate",
            "name": "Generate function cases",
            "projectId": "project-1",
            "sprintId": "sprint-1",
            "requirementId": "requirement-1",
            "sourceType": "text",
            "sourceContent": "requirement doc",
            "documentDownloadUrl": ("/internal/ai-worker/tasks/worker-task-1/requirement-document"),
            "instruction": "cover edge cases",
        },
    }


@pytest.mark.asyncio
async def test_functional_case_worker_snapshot_exposes_requirement_document_url():
    task = SimpleNamespace(
        task_id="worker-task-1",
        task_type="functional_case_generate",
        domain="ai",
        run_id="run-1",
        generate_task_id="generate-task-1",
    )
    run = SimpleNamespace(
        run_id="run-1",
        checkpoint_enabled=False,
        current_stage="",
        config_json={},
        snapshot_json={
            "taskId": "generate-task-1",
            "runId": "run-1",
            "taskType": "functional_case_generate",
            "documentType": "docx",
            "documentDownloadUrl": "/v1/requirements/requirement-1/download",
            "sourceContent": "",
        },
    )

    class FakeSession:
        async def scalar(self, statement):
            return run

    payload = await worker_service_module.build_snapshot(FakeSession(), "ai", task)

    assert payload["run"]["documentDownloadUrl"] == (
        "/internal/ai-worker/tasks/worker-task-1/requirement-document"
    )
    assert payload["run"]["sourceContent"] == (
        "/internal/ai-worker/tasks/worker-task-1/requirement-document"
    )


@pytest.mark.asyncio
async def test_ai_worker_snapshot_returns_go_style_requirement_analysis_payload():
    task = SimpleNamespace(
        task_id="worker-task-1",
        task_type="requirement_analysis",
        domain="ai",
        run_id="run-1",
        generate_task_id="generate-task-1",
    )
    run = SimpleNamespace(
        run_id="run-1",
        checkpoint_enabled=False,
        current_stage="",
        config_json={"temperature": 0.2},
        snapshot_json={
            "taskId": "generate-task-1",
            "runId": "run-1",
            "taskType": "requirement_analysis",
            "name": "Analyze requirement",
            "projectId": "project-1",
            "sprintId": "sprint-1",
            "requirementId": "requirement-1",
            "documentType": "text",
            "documentDownloadUrl": "/v1/requirements/requirement-1/download",
            "sourceContent": "requirement doc",
            "instruction": "find ambiguities",
        },
    )

    class FakeSession:
        async def scalar(self, statement):
            return run

    payload = await worker_service_module.build_snapshot(FakeSession(), "ai", task)

    assert payload == {
        "taskType": "requirement_analysis",
        "checkpointEnabled": False,
        "currentStage": "",
        "configJson": '{"temperature":0.2}',
        "run": {
            "taskId": "generate-task-1",
            "runId": "run-1",
            "taskType": "requirement_analysis",
            "name": "Analyze requirement",
            "projectId": "project-1",
            "sprintId": "sprint-1",
            "requirementId": "requirement-1",
            "documentType": "text",
            "sourceContent": "requirement doc",
            "documentDownloadUrl": ("/internal/ai-worker/tasks/worker-task-1/requirement-document"),
            "instruction": "find ambiguities",
        },
    }


@pytest.mark.asyncio
async def test_ai_worker_progress_waiting_review_marks_checkpoint_run_waiting(monkeypatch):
    task = SimpleNamespace(
        task_id="worker-task-1",
        task_type="functional_case_generate",
        worker_id="worker-1",
        status="running",
        run_id="run-1",
        heartbeat_at=None,
        lease_expires_at=None,
        finished_at=None,
        error_message="",
    )
    run = SimpleNamespace(
        run_id="run-1",
        checkpoint_enabled=True,
        current_stage="requirement_analysis",
        stage_status="running",
        status="running",
        config_json={},
        result_yaml="",
        result_summary_json={},
        error_message="",
    )

    class FakeRepository(FakeWorkerRepository):
        async def get_ai_run(self, run_id: str):
            assert run_id == "run-1"
            return run

    async def fake_find_task(session, domain, task_id):
        assert domain == "ai"
        assert task_id == "worker-task-1"
        return task

    monkeypatch.setattr(worker_task_service_module, "find_task", fake_find_task)
    service = WorkerTaskService(FakeRepository(task))

    await service.progress(
        "worker-task-1",
        WorkerProgressRequest(
            workerId="worker-1",
            taskId="worker-task-1",
            runId="run-1",
            currentStage="requirement_analysis",
            stageStatus="waiting_review",
            configJson='{"enhancedText":"需求"}',
            resultYaml='{"cases":[]}',
            resultSummaryJson='{"status":"running"}',
        ),
    )

    assert task.status == "success"
    assert task.finished_at is not None
    assert run.status == "waiting_review"
    assert run.stage_status == "waiting_review"
    assert run.current_stage == "requirement_analysis"
    assert run.config_json == {"enhancedText": "需求"}
    assert run.result_summary_json == {"status": "running"}


@pytest.mark.asyncio
async def test_ai_worker_claim_includes_requirement_analysis_checkpoint_config():
    task = SimpleNamespace(
        task_id="worker-task-1",
        task_type="requirement_analysis",
        worker_id="",
        status="pending",
        run_id="run-1",
        generate_task_id="task-1",
        llm_connection_id="connection-1",
        heartbeat_at=None,
        lease_expires_at=None,
    )
    run = SimpleNamespace(
        run_id="run-1",
        project_id="project-1",
        sprint_id="sprint-1",
        requirement_id="requirement-1",
        checkpoint_enabled=True,
        current_stage="writing_requirement",
        stage_status="pending",
        status="pending",
        config_json={"firstStepOutput": "reviewed text"},
    )

    class FakeRepository(FakeWorkerRepository):
        async def claim_pending(self, domain: str):
            assert domain == "ai"
            return task

        async def get_ai_run(self, run_id: str):
            assert run_id == "run-1"
            return run

    service = WorkerTaskService(FakeRepository(task))

    payload = await service.claim("ai", WorkerClaimRequest(workerId="worker-1"))

    assert payload["taskType"] == "requirement_analysis"
    assert payload["checkpointEnabled"] is True
    assert payload["currentStage"] == "writing_requirement"
    assert payload["configJson"] == '{"firstStepOutput":"reviewed text"}'


@pytest.mark.asyncio
async def test_ai_worker_progress_requirement_analysis_extracting_text_waits_for_review(
    monkeypatch,
):
    task = SimpleNamespace(
        task_id="worker-task-1",
        task_type="requirement_analysis",
        worker_id="worker-1",
        status="running",
        run_id="run-1",
        heartbeat_at=None,
        lease_expires_at=None,
        finished_at=None,
        error_message="",
    )
    run = SimpleNamespace(
        run_id="run-1",
        checkpoint_enabled=True,
        current_stage="extracting_text",
        stage_status="running",
        status="running",
        config_json={},
        result_yaml="",
        result_summary_json={},
        error_message="",
    )

    class FakeRepository(FakeWorkerRepository):
        async def get_ai_run(self, run_id: str):
            assert run_id == "run-1"
            return run

    async def fake_find_task(session, domain, task_id):
        assert domain == "ai"
        assert task_id == "worker-task-1"
        return task

    monkeypatch.setattr(worker_task_service_module, "find_task", fake_find_task)
    service = WorkerTaskService(FakeRepository(task))

    await service.progress(
        "worker-task-1",
        WorkerProgressRequest(
            workerId="worker-1",
            taskId="worker-task-1",
            runId="run-1",
            currentStage="extracting_text",
            stageStatus="waiting_review",
            configJson='{"firstStepOutput":"enhanced text"}',
        ),
    )

    assert task.status == "success"
    assert run.status == "waiting_review"
    assert run.stage_status == "waiting_review"
    assert run.config_json == {"firstStepOutput": "enhanced text"}


def test_ai_worker_completion_accepts_output_yaml_alias_for_requirement_analysis():
    run = SimpleNamespace(
        status="running",
        snapshot_json={},
        current_stage="feature_understanding",
        stage_status="running",
        error_message="",
        config_json={},
        result_yaml="",
        result_summary_json={},
        finished_at=None,
        duration_ms=0,
    )

    worker_service_module.apply_ai_completion_to_run(
        run,
        WorkerTaskEventRequest(
            workerId="worker-1",
            taskId="worker-task-1",
            status="success",
            outputYaml="final requirement understanding",
        ),
    )

    assert run.status == "success"
    assert run.result_yaml == "final requirement understanding"


@pytest.mark.asyncio
async def test_api_collection_item_complete_creates_case_run_and_binds_item(monkeypatch):
    task = SimpleNamespace(
        task_id="task-1",
        run_id="collection-run-1",
        status="running",
        task_type="api_collection_run",
        worker_id="worker-1",
        collection_run_id="collection-run-1",
        collection_id="collection-1",
    )
    item = SimpleNamespace(
        item_id="item-1",
        collection_run_id="collection-run-1",
        case_id="case-1",
        case_run_id=None,
        status="running",
        started_at=None,
        finished_at=None,
        duration_ms=0,
        error_message="",
    )
    collection_run = SimpleNamespace(
        collection_run_id="collection-run-1",
        requirement_id="requirement-1",
        sprint_id="sprint-1",
        project_id="project-1",
        environment_id="env-1",
        trigger_user_id="user-1",
        trigger_type="manual",
    )

    class FakeApiItemRepository(FakeWorkerRepository):
        def __init__(self):
            super().__init__(task)
            self.added = []

        async def get_api_item(self, item_id: str):
            assert item_id == "item-1"
            return item

        async def get_api_collection_run(self, collection_run_id: str):
            assert collection_run_id == "collection-run-1"
            return collection_run

        def add(self, row):
            self.added.append(row)

    async def fake_find_task(session, domain, task_id):
        assert domain == "api"
        assert task_id == "task-1"
        return task

    async def fake_update_item_counts(session, collection_run_id):
        assert collection_run_id == "collection-run-1"

    saved_extract_vars = []

    async def fake_save_extracted_environment_vars(
        session, environment_id, extract_results, *, actor
    ):
        saved_extract_vars.append((environment_id, extract_results))
        return []

    repository = FakeApiItemRepository()
    monkeypatch.setattr(worker_task_service_module, "find_task", fake_find_task)
    monkeypatch.setattr(worker_task_service_module, "update_item_counts", fake_update_item_counts)
    monkeypatch.setattr(
        worker_task_service_module,
        "save_extracted_environment_vars",
        fake_save_extracted_environment_vars,
    )
    monkeypatch.setattr(worker_task_service_module, "new_id", lambda: "case-run-1", raising=False)
    service = WorkerTaskService(repository)
    body = WorkerTaskEventRequest(
        workerId="worker-1",
        runId="",
        caseId="case-1",
        status="success",
        startedAt="2026-06-26T14:44:00Z",
        finishedAt="2026-06-26T14:44:01Z",
        durationMs=1000,
        request={"method": "GET", "url": "https://api.example.test/ping"},
        response={"statusCode": 200, "body": "ok"},
        runtimeVarsJson={"token": "abc"},
        extractResults=[{"success": True, "varKey": "token", "value": "abc"}],
        assertResults=[{"success": True}],
    )

    await service.complete_api_collection_item("task-1", "item-1", body)

    assert item.case_run_id == "case-run-1"
    assert len(repository.added) == 1
    case_run = repository.added[0]
    assert case_run.run_id == "case-run-1"
    assert case_run.collection_run_id == "collection-run-1"
    assert case_run.case_id == "case-1"
    assert case_run.status == "success"
    assert case_run.request_snapshot_json == {
        "method": "GET",
        "url": "https://api.example.test/ping",
    }
    assert case_run.response_snapshot_json == {"statusCode": 200, "body": "ok"}
    assert case_run.runtime_vars_json == {"token": "abc"}
    assert case_run.extract_results_json == [{"success": True, "varKey": "token", "value": "abc"}]
    assert case_run.assert_results_json == [{"success": True}]
    assert saved_extract_vars == [
        ("env-1", [{"success": True, "varKey": "token", "value": "abc"}]),
    ]


def test_internal_ui_worker_snapshot_returns_direct_payload():
    class FakeWorkerService:
        async def snapshot(self, domain, task_id):
            assert domain == "ui"
            assert task_id == "task-1"
            return {
                "taskId": "task-1",
                "taskType": "case_debug",
                "runId": "run-1",
                "caseRun": {"runId": "run-1"},
            }

    app = create_app(worker_settings())
    app.dependency_overrides[get_worker_task_service] = lambda: FakeWorkerService()
    app.dependency_overrides[get_settings] = worker_settings
    client = TestClient(app)

    response = client.get(
        "/internal/ui-worker/tasks/task-1/snapshot",
        headers={"X-Worker-Token": "worker-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "taskId": "task-1",
        "taskType": "case_debug",
        "runId": "run-1",
        "caseRun": {"runId": "run-1"},
    }


@pytest.mark.asyncio
async def test_api_worker_claim_queues_owner_run_and_uses_go_lease_seconds():
    task = SimpleNamespace(
        task_id="task-1",
        task_type="api_case_debug",
        domain="api",
        run_id="run-1",
        suite_id="",
        case_id="case-1",
        collection_run_id="",
        collection_id="collection-1",
        generate_task_id="",
        status="pending",
        worker_id="",
        started_at=None,
        heartbeat_at=None,
        lease_expires_at=None,
    )
    run = SimpleNamespace(run_id="run-1", status="pending")

    class FakeApiWorkerRepository(FakeWorkerRepository):
        async def claim_pending(self, domain: str):
            return task if domain == "api" else None

        async def get_api_run(self, run_id: str):
            assert run_id == "run-1"
            return run

    service = WorkerTaskService(FakeApiWorkerRepository(task))

    payload = await service.claim("api", WorkerClaimRequest(workerId="worker-1"))

    assert payload["leaseSeconds"] == 30
    assert payload["taskId"] == "task-1"
    assert run.status == "queued"


def test_internal_ui_worker_started_returns_204_like_go_contract():
    class FakeWorkerService:
        async def started(self, domain, task_id, body):
            assert domain == "ui"
            assert task_id == "task-1"
            assert body.worker_id == "worker-1"
            return {"taskId": task_id}

    app = create_app(worker_settings())
    app.dependency_overrides[get_worker_task_service] = lambda: FakeWorkerService()
    app.dependency_overrides[get_settings] = worker_settings
    client = TestClient(app)

    response = client.post(
        "/internal/ui-worker/tasks/task-1/started",
        headers={"X-Worker-Token": "worker-token"},
        json={"workerId": "worker-1", "startedAt": "2026-06-28T14:08:00Z"},
    )

    assert response.status_code == 204
    assert not response.content


@pytest.mark.asyncio
async def test_ui_case_payload_keeps_steps_json_array_for_worker():
    class FakeSession:
        async def scalar(self, statement):
            return SimpleNamespace(
                case_id="case-1",
                suite_id="suite-1",
                name="Login",
                enabled=True,
                order_no=1,
                steps_json=[{"keyword": "goto", "url": "https://example.test"}],
            )

    payload = await worker_service_module.ui_case_payload(FakeSession(), "case-1")

    assert payload["stepsJson"] == [{"keyword": "goto", "url": "https://example.test"}]


def test_ui_suite_payload_includes_screenshot_policy_for_worker():
    payload = worker_service_module.ui_suite_payload(
        SimpleNamespace(
            suite_id="suite-1",
            name="Login Suite",
            headless=True,
            slow_mo_ms=100,
            viewport_width=1440,
            viewport_height=900,
            default_step_timeout_ms=30000,
            screenshot_policy="after_each_step",
        )
    )

    assert payload == {
        "suiteId": "suite-1",
        "name": "Login Suite",
        "headless": True,
        "slowMoMs": 100,
        "viewportWidth": 1440,
        "viewportHeight": 900,
        "defaultStepTimeoutMs": 30000,
        "screenshotPolicy": "after_each_step",
    }


def test_ui_suite_payload_defaults_screenshot_policy_for_worker():
    payload = worker_service_module.ui_suite_payload(
        SimpleNamespace(
            suite_id="suite-1",
            name="Login Suite",
            headless=None,
            slow_mo_ms=None,
            viewport_width=None,
            viewport_height=None,
            default_step_timeout_ms=None,
        )
    )

    assert payload["screenshotPolicy"] == "on_failure"


def test_ui_case_generate_ai_worker_http_lifecycle_and_token_contract():
    events = []

    class FakeWorkerService:
        async def claim(self, domain, body):
            assert domain == "ai"
            assert body.worker_id == "worker-1"
            events.append("claim")
            return {
                "taskId": "worker-task-1",
                "taskType": "ui_case_generate",
                "runId": "run-1",
                "generateTaskId": "generate-task-1",
            }

        async def snapshot(self, domain, task_id):
            assert (domain, task_id) == ("ai", "worker-task-1")
            events.append("snapshot")
            return {
                "taskType": "ui_case_generate",
                "sourceArchiveDownloadUrl": (
                    "/internal/ai-worker/tasks/worker-task-1/source-archive"
                ),
            }

        async def started(self, domain, task_id, body):
            assert (domain, task_id, body.worker_id) == (
                "ai",
                "worker-task-1",
                "worker-1",
            )
            events.append("started")

        async def heartbeat(self, domain, task_id, body):
            assert (domain, task_id, body.worker_id) == (
                "ai",
                "worker-task-1",
                "worker-1",
            )
            events.append("heartbeat")

        async def progress(self, task_id, body):
            assert (task_id, body.worker_id, body.current_stage) == (
                "worker-task-1",
                "worker-1",
                "generating",
            )
            events.append("progress")

        async def complete(self, domain, task_id, body):
            assert (domain, task_id, body.worker_id, body.status) == (
                "ai",
                "worker-task-1",
                "worker-1",
                "success",
            )
            events.append("complete")

    app = create_app(worker_settings())
    app.dependency_overrides[get_worker_task_service] = lambda: FakeWorkerService()
    app.dependency_overrides[get_settings] = worker_settings
    client = TestClient(app)
    headers = {"X-Worker-Token": "worker-token"}
    event = {"workerId": "worker-1", "taskId": "worker-task-1", "runId": "run-1"}

    unauthorized = client.post("/internal/ai-worker/tasks/claim", json={"workerId": "worker-1"})
    claimed = client.post(
        "/internal/ai-worker/tasks/claim", headers=headers, json={"workerId": "worker-1"}
    )
    snapshot = client.get("/internal/ai-worker/tasks/worker-task-1/snapshot", headers=headers)
    started = client.post(
        "/internal/ai-worker/tasks/worker-task-1/started", headers=headers, json=event
    )
    heartbeat_response = client.post(
        "/internal/ai-worker/tasks/worker-task-1/heartbeat", headers=headers, json=event
    )
    progress = client.patch(
        "/internal/ai-worker/tasks/worker-task-1/progress",
        headers=headers,
        json={**event, "currentStage": "generating", "stageStatus": "running"},
    )
    completed = client.post(
        "/internal/ai-worker/tasks/worker-task-1/completed",
        headers=headers,
        json={**event, "status": "success", "resultYaml": "cases: []"},
    )

    assert unauthorized.status_code == 401
    assert claimed.status_code == 200
    assert claimed.json()["taskType"] == "ui_case_generate"
    assert snapshot.status_code == 200
    assert snapshot.json()["taskType"] == "ui_case_generate"
    assert [started.status_code, heartbeat_response.status_code, progress.status_code] == [
        204,
        204,
        204,
    ]
    assert completed.status_code == 204
    assert events == ["claim", "snapshot", "started", "heartbeat", "progress", "complete"]


@pytest.fixture(autouse=True)
def worker_contract_authority(monkeypatch):
    """Queue payload unit tests supply an authorized dispatch.

    Actual membership, actor and revocation checks use real HTTP/database tests in
    test_project_membership_api.py, not these fake queue repositories.
    """

    async def authority(session, task, *, pending=False):
        return SimpleNamespace(actor="user-1", project_id="project-1")

    monkeypatch.setattr(worker_task_service_module, "authorize_execution", authority)
