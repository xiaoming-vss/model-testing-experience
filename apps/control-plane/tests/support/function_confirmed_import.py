"""Shared preparation for function confirmed import tests; no collected cases."""

from datetime import UTC, datetime
from types import SimpleNamespace

from authorization_database import AuthorizationDatabase
from fastapi.testclient import TestClient

from support.execution_writer import MemoryExecutionWriter
from testing_agent.api.deps import get_ai_generate_task_service, get_current_user_id
from testing_agent.app import create_app
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.services.ai_generate_task import AiGenerateTaskService


def approved_run() -> SimpleNamespace:
    return SimpleNamespace(
        run_id="run-1",
        task_id="task-1",
        requirement_id="requirement-1",
        sprint_id="sprint-1",
        project_id="project-1",
        trigger_user_id="user-1",
        trigger_type="manual",
        status="success",
        checkpoint_enabled=False,
        current_stage="",
        stage_status="",
        snapshot_json={},
        error_message="",
        config_json={},
        result_yaml="""cases:
  - case_id: candidate-login
    module: Login
    title: " login works "
    preconditions: New account exists
    steps: Enter new credentials
    expectedResults: New home page opens
    priority: P0
    caseType: regression
  - case_id: candidate-submit
    module: Checkout
    title: Submit order
    preconditions: Cart has an item
    steps: Click submit
    expectedResults: Order is created
    priority: P1
    caseType: functional
""",
        result_summary_json={},
        review_status="approved",
        import_status="pending",
        imported_targets=[],
        imported_at=None,
        import_migration_complete=True,
        reviewer_user_id="user-1",
        reviewed_at=datetime.now(UTC),
        review_comment="approved",
        duration_ms=0,
    )


class FunctionImportRepository:
    session = AuthorizationDatabase()

    def __init__(self, *, owner: str = "user-1"):
        self.run = approved_run()
        self.owner = owner
        login_suite = FunctionTestSuite(
            suite_id="suite-login",
            requirement_id="requirement-1",
            name="Login",
            description="",
        )
        existing_case = FunctionTestCase(
            case_id="case-existing",
            suite_id="suite-login",
            module="Login",
            title="LOGIN WORKS",
            preconditions="Old account exists",
            steps="Enter old credentials",
            expected_results="Old home page opens",
            priority="P2",
            case_type="smoke",
            order_no=1,
        )
        self.suites = {login_suite.suite_id: login_suite}
        self.cases = {existing_case.case_id: existing_case}
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0

    @property
    def suites_by_name(self):
        return {suite.name: suite for suite in self.suites.values()}

    async def get_run(self, run_id: str):
        return self.run if run_id == self.run.run_id else None

    async def get_run_for_update(self, run_id: str):
        return await self.get_run(run_id)

    async def get_task(self, task_id: str):
        if task_id != "task-1":
            return None
        return SimpleNamespace(
            task_id="task-1",
            task_type="functional_case_generate",
            creator_user_id="user-1",
            project_id="project-1",
        )

    async def get_requirement(self, requirement_id: str):
        if requirement_id != "requirement-1":
            return None
        return SimpleNamespace(requirement_id=requirement_id, sprint_id="sprint-1")

    async def get_sprint(self, sprint_id: str):
        if sprint_id != "sprint-1":
            return None
        return SimpleNamespace(sprint_id=sprint_id, project_id="project-1")

    async def get_project(self, project_id: str):
        if project_id != "project-1":
            return None
        return SimpleNamespace(project_id=project_id, user_id=self.owner)

    async def get_function_suite_by_requirement_and_name(self, requirement_id: str, name: str):
        return next(
            (
                suite
                for suite in self.suites.values()
                if suite.requirement_id == requirement_id and suite.name == name
            ),
            None,
        )

    async def list_function_cases(self, suite_id: str):
        return [case for case in self.cases.values() if case.suite_id == suite_id]

    async def get_case(self, case_id: str):
        return self.cases.get(case_id)

    async def max_function_case_order_by_suite(self, suite_id: str) -> int:
        return max(
            (case.order_no for case in self.cases.values() if case.suite_id == suite_id),
            default=0,
        )

    def add(self, row: object):
        self.added.append(row)
        if isinstance(row, FunctionTestSuite):
            self.suites[row.suite_id] = row
        if isinstance(row, FunctionTestCase):
            self.cases[row.case_id] = row

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, _row):
        return None


def import_client(repository: FunctionImportRepository) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_ai_generate_task_service] = lambda: AiGenerateTaskService(
        repository, execution_writer=MemoryExecutionWriter()
    )
    return TestClient(app)
