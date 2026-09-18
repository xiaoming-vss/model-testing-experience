from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from testing_agent.api.deps import get_ai_generate_task_service, get_current_user_id
from testing_agent.app import create_app


def _run(**overrides):
    values = {
        "run_id": "run-1",
        "task_id": "task-1",
        "requirement_id": "requirement-1",
        "sprint_id": "sprint-1",
        "project_id": "project-1",
        "trigger_user_id": "user-1",
        "trigger_type": "manual",
        "status": "success",
        "checkpoint_enabled": False,
        "current_stage": "",
        "stage_status": "",
        "snapshot_json": {},
        "error_message": "",
        "config_json": {},
        "result_yaml": "",
        "result_summary_json": {},
        "review_status": "approved",
        "import_status": "pending",
        "imported_targets": [],
        "imported_at": None,
        "import_migration_complete": True,
        "reviewer_user_id": "user-1",
        "reviewed_at": datetime(2026, 8, 1, tzinfo=UTC),
        "review_comment": "",
        "duration_ms": 100,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _get_run_detail(run):
    class FakeAiGenerateTaskService:
        async def owned_run(self, user_id, run_id, kind):
            assert (user_id, run_id, kind) == ("user-1", "run-1", "api")
            return run

    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_ai_generate_task_service] = lambda: FakeAiGenerateTaskService()
    return TestClient(app).get("/v1/api-case-generate-task-runs/run-1")


def test_run_detail_exposes_only_pending_generic_import_state():
    response = _get_run_detail(_run(review_status="pending"))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["importStatus"] == "pending"
    assert data["importedTargets"] == []
    assert data["importedAt"] is None
    assert data["importMigrationComplete"] is True
    assert "importedCollectionId" not in data


def test_run_detail_exposes_multiple_supported_import_target_types():
    imported_at = datetime(2026, 8, 1, 6, 30, tzinfo=UTC)
    targets = [
        {"targetType": "api_collection", "targetId": "collection-1"},
        {"targetType": "function_suite", "targetId": "function-suite-1"},
        {"targetType": "ui_suite", "targetId": "ui-suite-1"},
    ]

    response = _get_run_detail(
        _run(import_status="imported", imported_targets=targets, imported_at=imported_at)
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["importStatus"] == "imported"
    assert data["importedTargets"] == targets
    assert data["importedAt"] == "2026-08-01T06:30:00Z"
    assert data["importMigrationComplete"] is True
    assert "importedCollectionId" not in data


def test_openapi_run_contract_omits_legacy_imported_collection_id():
    app = create_app()

    schema = app.openapi()["components"]["schemas"]["AiGenerateTaskRunResponse"]

    assert "importedCollectionId" not in schema["properties"]
