from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from testing_agent.core.errors import AppError
from testing_agent.services.revision_attachment_access import revision_attachment_ticket
from testing_agent.services.revision_attachments import (
    attach_revision_attachments,
    normalize_attachment_file_ids,
)


def stored_file(**overrides):
    values = {
        "file_id": "file",
        "project_id": "project",
        "uploaded_by": "user",
        "purpose": "attachment",
        "content_type": "image/png",
        "filename": "login.png",
        "size": 1024,
        "status": "ready",
        "resource_type": "",
        "resource_id": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_normalizes_attachment_ids_and_rejects_invalid_shapes():
    assert normalize_attachment_file_ids(None) == []
    assert normalize_attachment_file_ids(["a", "b"]) == ["a", "b"]
    for value in (
        "file",
        ["a", "a"],
        ["a"] * 7,
        [""],
        [1],
    ):
        with pytest.raises(AppError):
            normalize_attachment_file_ids(value)


@pytest.mark.asyncio
async def test_attaches_image_to_run_and_freezes_metadata():
    files = SimpleNamespace(get=AsyncMock(return_value=stored_file()), attach=AsyncMock())
    result = await attach_revision_attachments(
        files,
        user_id="user",
        project_id="project",
        run_id="run",
        file_ids=["file"],
    )
    assert result == ({"fileId": "file", "filename": "login.png", "contentType": "image/png"},)
    files.attach.assert_awaited_once_with(
        "user", "file", "project", "ai_generate_run", "run", purpose="attachment"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["project", "uploader", "purpose", "content_type", "size"])
async def test_rejects_unowned_or_non_image_files(change):
    overrides = {
        "project": {"project_id": "other"},
        "uploader": {"uploaded_by": "other"},
        "purpose": {"purpose": "requirement"},
        "content_type": {"content_type": "application/pdf"},
        "size": {"size": 10 * 1024 * 1024 + 1},
    }[change]
    files = SimpleNamespace(
        get=AsyncMock(return_value=stored_file(**overrides)), attach=AsyncMock()
    )
    with pytest.raises(AppError):
        await attach_revision_attachments(
            files,
            user_id="user",
            project_id="project",
            run_id="run",
            file_ids=["file"],
        )
    files.attach.assert_not_awaited()


def ticket_inputs(monkeypatch):
    task = SimpleNamespace(
        task_type="requirement_analysis",
        worker_id="worker",
        status="running",
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=1),
        run_id="run",
    )
    run = SimpleNamespace(run_id="run", project_id="project")
    image = stored_file(
        resource_type="ai_generate_run",
        resource_id="run",
        status="attached",
    )
    service = SimpleNamespace(
        repository=SimpleNamespace(
            session=object(),
            get_worker_task=AsyncMock(return_value=task),
            get_ai_run=AsyncMock(return_value=run),
        )
    )
    from testing_agent.services.stage_storage.worker_service import DirectStageWorkerService

    monkeypatch.setattr(DirectStageWorkerService, "is_direct", AsyncMock(return_value=True))
    monkeypatch.setattr(
        DirectStageWorkerService,
        "authorize",
        AsyncMock(
            return_value=SimpleNamespace(
                task=SimpleNamespace(project_id="project"),
                attempt_id="run",
                input_snapshot={"config": {"revisionAttachments": [{"fileId": "file"}]}},
            )
        ),
    )
    files = SimpleNamespace(
        get=AsyncMock(return_value=image),
        ticket=AsyncMock(return_value={"url": "signed"}),
    )
    return service, files, task, image


@pytest.mark.asyncio
async def test_revision_attachment_ticket(monkeypatch):
    service, files, _, _ = ticket_inputs(monkeypatch)
    assert await revision_attachment_ticket("task", "file", "worker", service, files) == {
        "url": "signed"
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    ["worker", "lease", "task_type", "project", "resource", "purpose", "status", "content"],
)
async def test_revision_attachment_access_boundaries(change, monkeypatch):
    service, files, task, image = ticket_inputs(monkeypatch)
    if change == "worker":
        task.worker_id = "other"
    if change == "lease":
        task.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    if change == "task_type":
        task.task_type = "ui_case_generate"
    if change == "project":
        image.project_id = "other"
    if change == "resource":
        image.resource_id = "other"
    if change == "purpose":
        image.purpose = "requirement"
    if change == "status":
        image.status = "ready"
    if change == "content":
        image.content_type = "image/svg+xml"
    with pytest.raises(AppError):
        await revision_attachment_ticket("task", "file", "worker", service, files)
    files.ticket.assert_not_awaited()


def test_revision_attachment_route_requires_worker_token_and_disables_cache(monkeypatch):
    from fastapi.testclient import TestClient

    from testing_agent.api.deps import get_file_service, get_worker_task_service
    from testing_agent.app import create_app
    from testing_agent.core.config import Settings, get_settings

    settings = Settings.from_mapping({"security": {"worker": {"key": "worker-token"}}})
    service, files, _, _ = ticket_inputs(monkeypatch)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_worker_task_service] = lambda: service
    app.dependency_overrides[get_file_service] = lambda: files
    with TestClient(app) as client:
        path = "/internal/ai-worker/tasks/task/revision-attachments/file?workerId=worker"
        assert client.get(path).status_code == 401
        response = client.get(path, headers={"X-Worker-Token": "worker-token"})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["url"] == "signed"


@pytest.mark.asyncio
async def test_run_attachment_access_requires_existing_run():
    from testing_agent.services.stored_file_access import require_file_resource

    image = stored_file(
        resource_type="ai_generate_run",
        resource_id="run",
        status="attached",
    )
    attempt = SimpleNamespace(
        input_snapshot_json={"config": {"revisionAttachments": [{"fileId": "file"}]}}
    )
    session = SimpleNamespace(scalars=AsyncMock(return_value=[attempt]))
    await require_file_resource(session, image)
    session.scalars.return_value = []
    with pytest.raises(AppError):
        await require_file_resource(session, image)
