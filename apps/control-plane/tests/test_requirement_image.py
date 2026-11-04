from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from testing_agent.core.errors import AppError
from testing_agent.services.requirement_image import requirement_image_ticket


def inputs(monkeypatch):
    task = SimpleNamespace(
        task_type="requirement_analysis",
        worker_id="worker",
        status="running",
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=1),
        run_id="run",
    )
    requirement = SimpleNamespace(
        document_type="richtext", document_file_id="doc", requirement_id="r"
    )
    doc = SimpleNamespace(
        project_id="p",
        resource_type="requirement",
        resource_id="r",
        purpose="requirement",
        status="attached",
        object_key="html",
    )
    img = SimpleNamespace(
        project_id="p",
        resource_type="requirement",
        resource_id="r",
        purpose="attachment",
        status="attached",
        content_type="image/png",
    )
    service = SimpleNamespace(
        requirement_document=AsyncMock(return_value=requirement),
        repository=SimpleNamespace(
            session=object(),
            get_worker_task=AsyncMock(return_value=task),
            get_ai_run=AsyncMock(return_value=SimpleNamespace(project_id="p")),
        ),
    )
    from testing_agent.services.stage_storage.worker_service import DirectStageWorkerService

    monkeypatch.setattr(DirectStageWorkerService, "is_direct", AsyncMock(return_value=True))
    monkeypatch.setattr(
        DirectStageWorkerService,
        "authorize",
        AsyncMock(return_value=SimpleNamespace(task=SimpleNamespace(project_id="p"))),
    )
    files = SimpleNamespace(
        get=AsyncMock(side_effect=[doc, img]),
        storage=SimpleNamespace(read_text=lambda key: '<img data-file-id="image">'),
        ticket=AsyncMock(return_value={"url": "signed"}),
    )
    return service, files, task, img


@pytest.mark.asyncio
async def test_referenced_image_ticket(monkeypatch):
    service, files, _, _ = inputs(monkeypatch)
    assert await requirement_image_ticket("task", "image", "worker", service, files) == {
        "url": "signed"
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["worker", "lease", "project", "requirement", "reference", "status", "authority"]
)
async def test_image_access_boundaries(change, monkeypatch):
    service, files, task, img = inputs(monkeypatch)
    if change == "worker":
        task.worker_id = "other"
    if change == "lease":
        task.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    if change == "project":
        img.project_id = "other"
    if change == "requirement":
        img.resource_id = "other"
    if change == "reference":
        files.storage.read_text = lambda key: "<p>No image</p>"
    if change == "status":
        task.status = "success"
    if change == "authority":
        service.requirement_document.side_effect = AppError(409, "source changed", 409)
    with pytest.raises(AppError):
        await requirement_image_ticket("task", "image", "worker", service, files)
    files.ticket.assert_not_awaited()


def test_image_route_requires_worker_token_and_disables_cache(monkeypatch):
    from fastapi.testclient import TestClient

    from testing_agent.api.deps import get_file_service, get_worker_task_service
    from testing_agent.app import create_app
    from testing_agent.core.config import Settings, get_settings

    settings = Settings.from_mapping({"security": {"worker": {"key": "worker-token"}}})
    service, files, _, _ = inputs(monkeypatch)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_worker_task_service] = lambda: service
    app.dependency_overrides[get_file_service] = lambda: files
    with TestClient(app) as client:
        path = "/internal/ai-worker/tasks/task/requirement-images/image?workerId=worker"
        assert client.get(path).status_code == 401
        response = client.get(path, headers={"X-Worker-Token": "worker-token"})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["url"] == "signed"


def test_richtext_retry_uses_current_worker_document_endpoint():
    from testing_agent.services.stage_storage.payload import worker_payloads

    source = {
        "taskType": "requirement_analysis",
        "documentType": "richtext",
        "documentDownloadUrl": "/internal/ai-worker/tasks/old/requirement-document",
    }
    task = SimpleNamespace(
        task_id="generate-task",
        task_type="requirement_analysis",
        name="需求分析",
        project_id="p",
        sprint_id="s",
        requirement_id="r",
    )
    authority = SimpleNamespace(
        task=task,
        attempt_id="run",
        revision_instruction=None,
        input_snapshot={"source": source, "config": {}, "llmConnectionId": "llm"},
    )
    worker = SimpleNamespace(task_id="retry")
    result = worker_payloads(authority, worker, stage_name="extracting_text", lease_seconds=30)[1]
    assert (
        result["run"]["documentDownloadUrl"]
        == "/internal/ai-worker/tasks/retry/requirement-document"
    )
