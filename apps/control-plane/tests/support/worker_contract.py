"""Shared preparation for worker contract tests; no collected cases."""

from types import SimpleNamespace

import pytest

from testing_agent.core.config import Settings
from testing_agent.services import worker_task as worker_task_service_module


class FakeWorkerRepository:
    def __init__(self, task=None):
        self.session = SimpleNamespace()
        self.task = task

    async def execution_context(self, task):
        from testing_agent.domain.worker_context import (
            AiWorkerContext,
            ApiWorkerContext,
            UiWorkerContext,
        )

        if task.domain == "ai":
            return AiWorkerContext(task.generate_task_id, task.llm_connection_id)
        if task.domain == "api":
            return ApiWorkerContext(task.case_id, task.collection_id, task.collection_run_id)
        return UiWorkerContext(task.case_id, task.suite_id)

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


@pytest.fixture(autouse=True)
def worker_contract_authority(monkeypatch):
    """Queue payload unit tests supply an authorized dispatch.

    Actual membership, actor and revocation checks use real HTTP/database tests in
    test_project_membership_api.py, not these fake queue repositories.
    """

    async def authority(session, task, *, pending=False):
        return SimpleNamespace(actor="user-1", project_id="project-1")

    monkeypatch.setattr(worker_task_service_module, "authorize_execution", authority)
