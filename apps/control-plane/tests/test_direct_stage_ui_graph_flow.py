"""Direct-stage transaction and worker/view regression tests."""

import json

import pytest
from support.ai_execution import AsyncSessionAdapter, seed_task  # noqa: F401
from support.ai_execution import db as db
from support.direct_stage_storage import (
    TRACEABLE_CONFIG,
    TRACEABLE_POINTS,
    TRACEABLE_SOURCE,
    setup_stage,
)

from testing_agent.core.errors import AppError


async def test_stage_http_edit_and_review_use_direct_attempt(db):  # noqa: F811
    import httpx
    from support.generation import generation_services, install_generation_services

    from testing_agent.api.deps import get_current_user_id
    from testing_agent.app import create_app
    from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository

    stage, storage = setup_stage(db)
    candidate = await storage.prepare(
        stage.id,
        worker_task_id="worker",
        requested_by="u",
        input_snapshot={"source": TRACEABLE_SOURCE, "config": TRACEABLE_CONFIG},
    )
    await storage.publish(
        stage.id,
        attempt_id=candidate.id,
        worker_task_id="worker",
        content=json.dumps(TRACEABLE_POINTS),
        output_format="json",
        output_context=None,
    )
    db.commit()
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "u"
    install_generation_services(
        app, generation_services(AiGenerateTaskRepository(AsyncSessionAdapter(db)))
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        overview = await client.get("/v1/requirements/r/generation")
        assert overview.status_code == 200, overview.text
        detail = await client.get("/v1/requirements/r/generation/function")
        assert detail.status_code == 200, detail.text
        saved = await client.put(
            "/v1/requirements/r/generation/function/stages/case_names/draft",
            json={"expectedAttemptId": candidate.id, "content": json.dumps(TRACEABLE_POINTS)},
        )
        assert saved.status_code == 404, saved.text
        approved = await client.post(
            "/v1/requirements/r/generation/function/stages/case_names/review",
            json={"action": "approve", "expectedAttemptId": candidate.id},
        )
        assert approved.status_code == 404, approved.text


async def test_direct_revision_attachment_owner_requires_frozen_file_reference(db):  # noqa: F811
    from types import SimpleNamespace

    from testing_agent.services.stored_file_access import require_file_resource

    stage, storage = setup_stage(db)
    attempt = await storage.prepare(
        stage.id,
        worker_task_id="worker",
        requested_by="u",
        input_snapshot={"config": {"revisionAttachments": [{"fileId": "file"}]}},
    )
    row = SimpleNamespace(
        status="attached",
        resource_id=attempt.id,
        resource_type="ai_generate_run",
        project_id="p",
        purpose="attachment",
        file_id="file",
    )
    await require_file_resource(AsyncSessionAdapter(db), row)
    row.file_id = "other"
    with pytest.raises(AppError):
        await require_file_resource(AsyncSessionAdapter(db), row)
