from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from testing_agent.core.errors import AppError
from testing_agent.services.requirement_image import requirement_image_ticket


def inputs():
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
            get_worker_task=AsyncMock(return_value=task),
            get_ai_run=AsyncMock(return_value=SimpleNamespace(project_id="p")),
        ),
    )
    files = SimpleNamespace(
        get=AsyncMock(side_effect=[doc, img]),
        storage=SimpleNamespace(read_text=lambda key: '<img data-file-id="image">'),
        ticket=AsyncMock(return_value={"url": "signed"}),
    )
    return service, files, task, img


@pytest.mark.asyncio
async def test_referenced_image_ticket():
    service, files, _, _ = inputs()
    assert await requirement_image_ticket("task", "image", "worker", service, files) == {
        "url": "signed"
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["worker", "lease", "project", "requirement", "reference", "status", "authority"]
)
async def test_image_access_boundaries(change):
    service, files, task, img = inputs()
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


def test_image_route_requires_worker_token_and_disables_cache():
    from fastapi.testclient import TestClient

    from testing_agent.api.deps import get_file_service, get_worker_task_service
    from testing_agent.app import create_app
    from testing_agent.core.config import Settings, get_settings

    settings = Settings.from_mapping({"security": {"worker": {"key": "worker-token"}}})
    service, files, _, _ = inputs()
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


@pytest.mark.asyncio
async def test_richtext_retry_uses_current_worker_document_endpoint():
    from testing_agent.services.worker import build_snapshot

    run = SimpleNamespace(
        run_id="run",
        checkpoint_enabled=True,
        current_stage="extracting_text",
        config_json={},
        snapshot_json={
            "taskType": "requirement_analysis",
            "documentType": "richtext",
            "documentDownloadUrl": "/internal/ai-worker/tasks/old/requirement-document",
        },
    )
    task = SimpleNamespace(task_id="retry", run_id="run", task_type="requirement_analysis")
    result = await build_snapshot(SimpleNamespace(scalar=AsyncMock(return_value=run)), "ai", task)
    assert (
        result["run"]["documentDownloadUrl"]
        == "/internal/ai-worker/tasks/retry/requirement-document"
    )
