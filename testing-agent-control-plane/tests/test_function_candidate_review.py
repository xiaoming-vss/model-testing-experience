from types import SimpleNamespace

from authorization_database import AuthorizationDatabase
from fastapi.testclient import TestClient

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
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_ai_generate_task_service] = lambda: AiGenerateTaskService(
        repository
    )
    return TestClient(app)


def test_function_candidate_can_be_edited_then_approval_freezes_without_importing():
    run = make_run()
    repository = FunctionReviewRepository(run)
    client = review_client(repository)
    candidate = """cases:
  - module: Login
    title: Successful login
    preconditions: Account exists
    steps: Enter credentials
    expectedResults: Home page opens
    priority: P1
    caseType: functional
"""

    saved = client.patch(
        "/v1/function-case-generate-task-runs/run-1/result",
        json={"resultYaml": candidate},
    )
    approved = client.post(
        "/v1/function-case-generate-task-runs/run-1/review",
        json={"action": "approve", "reviewComment": "looks good"},
    )
    frozen = client.patch(
        "/v1/function-case-generate-task-runs/run-1/result",
        json={"resultYaml": "cases: []"},
    )

    assert saved.status_code == 200
    assert saved.json()["data"]["resultYaml"] == candidate
    assert approved.status_code == 200
    assert approved.json()["data"]["reviewStatus"] == "approved"
    assert approved.json()["data"]["importStatus"] == "pending"
    assert approved.json()["data"]["importedTargets"] == []
    assert frozen.status_code == 400
    assert run.result_yaml == candidate
    assert repository.commits == 2


def test_only_successful_function_run_can_be_approved():
    run = make_run(status="failed")
    client = review_client(FunctionReviewRepository(run))

    response = client.post(
        "/v1/function-case-generate-task-runs/run-1/review",
        json={"action": "approve"},
    )

    assert response.status_code == 400
    assert run.review_status == "pending"
