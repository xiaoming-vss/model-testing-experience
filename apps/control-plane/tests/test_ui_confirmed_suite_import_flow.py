from datetime import UTC, datetime
from types import SimpleNamespace

from authorization_database import AuthorizationDatabase
from fastapi.testclient import TestClient

from testing_agent.api.deps import (
    get_ai_generate_task_service,
    get_current_user_id,
    get_ui_test_case_service,
)
from testing_agent.app import create_app
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.services.ai_generate_task import AiGenerateTaskService
from testing_agent.services.ui_test_case import UiTestCaseService


def approved_ui_run():
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
  - name: " login "
    enabled: false
    orderNo: 7
    stepsJson:
      - orderNo: 1
        stepName: Enter username
        keyword: fill
        locatorType: test_id
        locatorValue: username
        operationValue: alice
        continueOnFailure: true
        enabled: false
  - name: Health
    enabled: true
    orderNo: 8
    stepsJson:
      - orderNo: 1
        stepName: Open health
        keyword: open
        operationValue: https://example.test/health
        continueOnFailure: false
        enabled: true
""",
        result_summary_json={},
        review_status="approved",
        import_status="pending",
        imported_targets=[],
        imported_at=None,
        import_migration_complete=True,
        reviewer_user_id="user-1",
        reviewed_at=datetime.now(UTC),
        review_comment="ready",
        duration_ms=0,
    )


class UiImportRepository:
    session = AuthorizationDatabase()

    def __init__(self):
        self.run = approved_ui_run()
        self.project = SimpleNamespace(project_id="project-1", user_id="user-1")
        self.sprint = SimpleNamespace(sprint_id="sprint-1", project_id="project-1")
        self.requirement = SimpleNamespace(requirement_id="requirement-1", sprint_id="sprint-1")
        self.suite = SimpleNamespace(
            suite_id="suite-1", requirement_id="requirement-1"
        )
        now = datetime.now(UTC)
        existing = UiTestCase(
            case_id="case-existing",
            suite_id="suite-1",
            name="Login",
            enabled=True,
            order_no=1,
            steps_json=[
                {
                    "orderNo": 1,
                    "stepName": "Open login",
                    "keyword": "open",
                    "operationValue": "https://example.test/login",
                    "continueOnFailure": False,
                    "enabled": True,
                }
            ],
        )
        existing.created_at = now
        existing.updated_at = now
        self.cases = [existing]
        self.pending = []
        self.commits = 0

    async def get_run(self, run_id):
        return self.run if run_id == self.run.run_id else None

    async def get_run_for_update(self, run_id):
        return await self.get_run(run_id)

    async def get_task(self, task_id):
        if task_id != "task-1":
            return None
        return SimpleNamespace(
            task_id="task-1",
            task_type="ui_case_generate",
            creator_user_id="user-1",
            project_id="project-1",
        )

    async def get_project(self, project_id):
        return self.project if project_id == self.project.project_id else None

    async def get_sprint(self, sprint_id):
        return self.sprint if sprint_id == self.sprint.sprint_id else None

    async def get_requirement(self, requirement_id):
        return self.requirement if requirement_id == self.requirement.requirement_id else None

    async def get_ui_suite(self, suite_id):
        return self.suite if suite_id == self.suite.suite_id else None

    async def get_suite(self, suite_id):
        return await self.get_ui_suite(suite_id)

    async def list_ui_cases(self, suite_id):
        return [case for case in self.cases if case.suite_id == suite_id]

    async def list_by_suite(self, suite_id):
        return await self.list_ui_cases(suite_id)

    def add(self, row):
        self.pending.append(row)

    async def commit(self):
        now = datetime.now(UTC)
        for row in self.pending:
            row.created_at = now
            row.updated_at = now
            self.cases.append(row)
        self.pending.clear()
        self.commits += 1

    async def rollback(self):
        self.pending.clear()

    async def refresh(self, _row):
        return None


def ui_import_client(repository):
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_ai_generate_task_service] = lambda: AiGenerateTaskService(
        repository
    )
    app.dependency_overrides[get_ui_test_case_service] = lambda: UiTestCaseService(repository)
    return TestClient(app, raise_server_exceptions=False)


def test_ui_import_previews_full_conflict_then_confirms_in_place_and_only_once():
    repository = UiImportRepository()
    client = ui_import_client(repository)

    preview = client.post(
        "/v1/ui-case-generate-task-runs/run-1/import",
        json={"suiteId": "suite-1"},
    )

    assert preview.status_code == 200
    data = preview.json()["data"]
    assert data["requiresConfirmation"] is True
    assert data["conflicts"] == [
        {
            "normalizedName": "login",
            "existingCase": {
                "name": "Login",
                "enabled": True,
                "orderNo": 1,
                "stepsJson": repository.cases[0].steps_json,
            },
            "generatedCase": {
                "name": " login ",
                "enabled": False,
                "orderNo": 7,
                "stepsJson": [
                    {
                        "orderNo": 1,
                        "stepName": "Enter username",
                        "keyword": "fill",
                        "locatorType": "test_id",
                        "locatorValue": "username",
                        "operationValue": "alice",
                        "continueOnFailure": True,
                        "enabled": False,
                    }
                ],
            },
        }
    ]
    assert len(repository.cases) == 1
    assert repository.commits == 0
    assert repository.run.review_status == "approved"
    assert repository.run.import_status == "pending"

    confirmed = client.post(
        "/v1/ui-case-generate-task-runs/run-1/import",
        json={"suiteId": "suite-1", "confirmOverwrite": True},
    )
    formal_cases = client.get("/v1/ui-test-suites/suite-1/cases")
    run_status = client.get("/v1/ui-case-generate-task-runs/run-1")
    repeated = client.post(
        "/v1/ui-case-generate-task-runs/run-1/import",
        json={"suiteId": "suite-1", "confirmOverwrite": True},
    )

    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["requiresConfirmation"] is False
    assert formal_cases.status_code == 200
    imported = formal_cases.json()["data"]["items"]
    assert [case["caseId"] for case in imported] == ["case-existing", imported[1]["caseId"]]
    assert imported[0]["name"] == " login "
    assert imported[0]["enabled"] is False
    assert imported[0]["orderNo"] == 7
    assert imported[0]["stepsJson"][0]["locatorValue"] == "username"
    assert imported[1]["name"] == "Health"
    assert run_status.status_code == 200
    assert run_status.json()["data"]["reviewStatus"] == "approved"
    assert run_status.json()["data"]["importStatus"] == "imported"
    assert run_status.json()["data"]["importedTargets"] == [
        {"targetType": "ui_suite", "targetId": "suite-1"}
    ]
    assert run_status.json()["data"]["importedAt"] is not None
    assert repeated.status_code == 400
