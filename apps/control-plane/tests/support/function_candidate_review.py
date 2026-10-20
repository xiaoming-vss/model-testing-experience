"""Shared preparation for function candidate review tests; no collected cases."""

from types import SimpleNamespace

from authorization_database import AuthorizationDatabase
from fastapi.testclient import TestClient

from support.execution_writer import MemoryExecutionWriter
from testing_agent.api.deps import get_ai_generate_task_service, get_current_user_id
from testing_agent.app import create_app
from testing_agent.services.ai_generate_task import AiGenerateTaskService


def make_run(*, status: str = "success") -> SimpleNamespace:
    return SimpleNamespace(
        run_id="run-1",
        task_id="task-1",
        requirement_id="requirement-1",
        sprint_id="sprint-1",
        project_id="project-1",
        trigger_user_id="user-1",
        trigger_type="manual",
        status=status,
        checkpoint_enabled=False,
        current_stage="",
        stage_status="",
        snapshot_json={},
        error_message="",
        config_json={},
        result_yaml="cases: []",
        result_summary_json={},
        review_status="pending",
        import_status="pending",
        imported_targets=[],
        imported_at=None,
        import_migration_complete=True,
        reviewer_user_id="",
        reviewed_at=None,
        review_comment="",
        duration_ms=0,
    )


class FunctionReviewRepository:
    session = AuthorizationDatabase()

    def __init__(self, run: SimpleNamespace):
        self.run = run
        self.commits = 0

    async def get_project(self, project_id):
        from sqlalchemy import select

        from testing_agent.models.project import Project

        return await self.session.scalar(select(Project).where(Project.project_id == project_id))

    async def get_run(self, run_id: str):
        return self.run if run_id == self.run.run_id else None

    async def get_task(self, task_id: str):
        if task_id != "task-1":
            return None
        return SimpleNamespace(
            task_id="task-1",
            task_type="functional_case_generate",
            creator_user_id="user-1",
            project_id="project-1",
        )

    async def commit(self):
        self.commits += 1

    async def refresh(self, _row):
        return None


def review_client(repository: FunctionReviewRepository) -> TestClient:
    app = create_app()
    writer = MemoryExecutionWriter()
    app.state.execution_writer = writer
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_ai_generate_task_service] = lambda: AiGenerateTaskService(
        repository, execution_writer=writer
    )
    return TestClient(app)
