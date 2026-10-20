"""Shared preparation for api review confirmed import tests; no collected cases."""

from datetime import UTC, datetime
from types import SimpleNamespace

from authorization_database import AuthorizationDatabase, AuthorizedRepositoryFixture
from fastapi.testclient import TestClient

from support.execution_writer import MemoryExecutionWriter
from testing_agent.api.deps import (
    get_ai_generate_task_service,
    get_api_case_service,
    get_current_user_id,
)
from testing_agent.app import create_app
from testing_agent.models.api_assert_rule import ApiAssertRule
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_extract_rule import ApiExtractRule
from testing_agent.services.ai_generate_task import AiGenerateTaskService
from testing_agent.services.api_case import ApiCaseService


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


class ReviewRepository(AuthorizedRepositoryFixture):
    def __init__(self, run: SimpleNamespace):
        self.run = run
        self.commits = 0

    async def get_run(self, run_id: str):
        return self.run if run_id == self.run.run_id else None

    async def get_task(self, task_id: str):
        if task_id != "task-1":
            return None
        return SimpleNamespace(
            task_id="task-1",
            task_type="api_case_generate",
            creator_user_id="user-1",
            project_id="project-1",
        )

    async def commit(self):
        self.commits += 1

    async def refresh(self, _row):
        return None


def review_client(repository: ReviewRepository) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_ai_generate_task_service] = lambda: AiGenerateTaskService(
        repository, execution_writer=MemoryExecutionWriter()
    )
    return TestClient(app)


class ImportRepository(ReviewRepository):
    session = AuthorizationDatabase()

    def __init__(self, run: SimpleNamespace, *, owner: str = "user-1"):
        super().__init__(run)
        now = datetime.now(UTC)
        self.projects = {
            "project-1": SimpleNamespace(project_id="project-1", user_id="user-1"),
            "target-project": SimpleNamespace(project_id="target-project", user_id=owner),
        }
        self.sprints = {
            "target-sprint": SimpleNamespace(sprint_id="target-sprint", project_id="target-project")
        }
        self.requirements = {
            "target-requirement": SimpleNamespace(
                requirement_id="target-requirement", sprint_id="target-sprint"
            )
        }
        self.collections = {
            "collection-1": SimpleNamespace(
                collection_id="collection-1",
                requirement_id="target-requirement",
            )
        }
        existing = ApiCase(
            case_id="case-existing",
            collection_id="collection-1",
            name="Login",
            description="old description",
            enabled=True,
            order_no=1,
            method="GET",
            url_template="/old-login",
            headers_json={"X-Version": "old"},
            query_json={"old": "query"},
            body_type="json",
            body_json={"old": True},
            body_text="",
            timeout_ms=1000,
            continue_on_failure=False,
        )
        existing.created_at = now
        existing.updated_at = now
        self.cases = [existing]
        extract = ApiExtractRule(
            extract_rule_id="extract-existing",
            case_id="case-existing",
            name="old token",
            enabled=True,
            order_no=0,
            source="body_jsonpath",
            source_expr="$.old",
            var_key="token",
            default_value="old",
        )
        extract.created_at = now
        extract.updated_at = now
        self.extract_rules = [extract]
        assertion = ApiAssertRule(
            assert_rule_id="assert-existing",
            case_id="case-existing",
            name="old status",
            enabled=True,
            order_no=0,
            assert_source="status_code",
            target_expr="",
            comparator="eq",
            expected_value="201",
        )
        assertion.created_at = now
        assertion.updated_at = now
        self.assert_rules = [assertion]
        self.pending = []
        self.pending_deletes = []
        self.fail_next_commit = False

    async def get_collection(self, collection_id: str):
        return self.collections.get(collection_id)

    async def get_requirement(self, requirement_id: str):
        return self.requirements.get(requirement_id)

    async def get_sprint(self, sprint_id: str):
        return self.sprints.get(sprint_id)

    async def get_project(self, project_id: str):
        return self.projects.get(project_id)

    async def exists_case_by_collection_and_name(self, collection_id: str, name: str):
        normalized = name.strip().casefold()
        return any(
            case.collection_id == collection_id and case.name.strip().casefold() == normalized
            for case in self.cases
        )

    async def list_api_cases(self, collection_id: str):
        return [case for case in self.cases if case.collection_id == collection_id]

    async def list_cases(self, collection_id: str):
        return await self.list_api_cases(collection_id)

    async def list_api_extract_rules(self, case_id: str):
        return [rule for rule in self.extract_rules if rule.case_id == case_id]

    async def list_api_assert_rules(self, case_id: str):
        return [rule for rule in self.assert_rules if rule.case_id == case_id]

    def add(self, row):
        self.pending.append(row)

    async def delete(self, row):
        self.pending_deletes.append(row)

    async def flush(self):
        return None

    async def commit(self):
        if self.fail_next_commit:
            self.fail_next_commit = False
            raise RuntimeError("database unavailable")
        now = datetime.now(UTC)
        for row in self.pending_deletes:
            for collection in (self.extract_rules, self.assert_rules):
                if row in collection:
                    collection.remove(row)
        for row in self.pending:
            if not hasattr(row, "created_at"):
                row.created_at = now
            if not hasattr(row, "updated_at"):
                row.updated_at = now
            if isinstance(row, ApiCase):
                self.cases.append(row)
            elif isinstance(row, ApiExtractRule):
                self.extract_rules.append(row)
            elif isinstance(row, ApiAssertRule):
                self.assert_rules.append(row)
        self.pending.clear()
        self.pending_deletes.clear()
        await super().commit()

    async def rollback(self):
        self.pending.clear()
        self.pending_deletes.clear()


def import_client(repository: ImportRepository) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_ai_generate_task_service] = lambda: AiGenerateTaskService(
        repository, execution_writer=MemoryExecutionWriter()
    )
    app.dependency_overrides[get_api_case_service] = lambda: ApiCaseService(repository)
    return TestClient(app, raise_server_exceptions=False)


def approved_import_run() -> SimpleNamespace:
    run = make_run()
    run.review_status = "approved"
    run.reviewer_user_id = "user-1"
    run.reviewed_at = datetime.now(UTC)
    run.result_yaml = """cases:
  - name: " login "
    description: new description
    enabled: false
    orderNo: 4
    method: POST
    urlTemplate: /new-login
    headers:
      X-Version: new
    query:
      page: "1"
    bodyType: json
    bodyJson:
      username: alice
    timeoutMs: 2500
    continueOnFailure: true
    extractRules:
      - name: new token
        source: body_jsonpath
        sourceExpr: $.token
        varKey: token
        defaultValue: missing
    assertRules:
      - name: new status
        assertSource: status_code
        comparator: eq
        expectedValue: "200"
  - name: Health
    method: GET
    urlTemplate: /health
"""
    return run
