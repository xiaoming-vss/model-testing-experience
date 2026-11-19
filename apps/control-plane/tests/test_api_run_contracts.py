from types import SimpleNamespace

import pytest
from authorization_database import AuthorizationDatabase

from testing_agent.schemas.api_run import RunApiCaseRequest
from testing_agent.services import worker
from testing_agent.services.api_case import ApiCaseService
from testing_agent.services.api_collection_run import ApiCollectionRunService
from testing_agent.services.api_request_render import (
    api_case_request_template,
    render_api_case_request,
)
from testing_agent.services.worker_domains.api import save_extracted_environment_vars


def test_api_case_request_render_matches_go_worker_snapshot_contract():
    api_case = SimpleNamespace(
        method="POST",
        url_template="/users/{{userId}}",
        headers_json={"Authorization": "Bearer {{token}}"},
        query_json={"q": "{{keyword}}"},
        body_type="json",
        body_json={"name": "{{keyword}}", "active": "{{enabled}}"},
        body_text="",
        timeout_ms=3000,
    )
    environment = SimpleNamespace(base_url="https://api.example.test/v1")
    env_vars = [
        SimpleNamespace(var_key="userId", value="42"),
        SimpleNamespace(var_key="token", value="secret"),
        SimpleNamespace(var_key="keyword", value="demo"),
        SimpleNamespace(var_key="enabled", value="true"),
    ]

    rendered = render_api_case_request(api_case, environment, env_vars)

    assert rendered.snapshot == {
        "method": "POST",
        "url": "https://api.example.test/v1/users/42",
        "headersJson": '{"Authorization":"Bearer secret"}',
        "queryJson": '{"q":"demo"}',
        "bodyType": "json",
        "body": '{"name":"demo","active":"true"}',
    }
    assert rendered.runtime_vars == {
        "userId": "42",
        "token": "secret",
        "keyword": "demo",
        "enabled": "true",
    }


def test_api_case_request_template_preserves_runtime_placeholders():
    api_case = SimpleNamespace(
        method="GET",
        url_template="/profile",
        headers_json={"Authorization": "Bearer {{token}}"},
        query_json={"tenant": "{{tenant}}"},
        body_type="none",
        body_json=None,
        body_text="",
        timeout_ms=3000,
    )
    environment = SimpleNamespace(base_url="https://api.example.test/{{tenant}}")

    assert api_case_request_template(api_case, environment) == {
        "method": "GET",
        "baseUrl": "https://api.example.test/{{tenant}}",
        "urlTemplate": "/profile",
        "headersJson": '{"Authorization":"Bearer {{token}}"}',
        "queryJson": '{"tenant":"{{tenant}}"}',
        "bodyType": "none",
        "bodyJson": "",
        "bodyText": "",
        "timeoutMs": 3000,
    }


@pytest.mark.asyncio
async def test_save_extracted_environment_vars_upserts_successful_results(monkeypatch):
    class FakeSession:
        def __init__(self):
            self.added = []

        async def scalar(self, statement):
            return None

        def add(self, row):
            self.added.append(row)

    session = FakeSession()
    monkeypatch.setattr("testing_agent.services.worker_domains.api.new_id", lambda: "env-var-1")

    await save_extracted_environment_vars(
        session,
        "env-1",
        [
            {"success": True, "varKey": "token", "value": "abc"},
            {"success": False, "varKey": "ignored", "value": "nope"},
            {"success": True, "varKey": "", "value": "empty"},
        ],
        actor="user-1",
    )

    assert len(session.added) == 1
    env_var = session.added[0]
    assert env_var.env_var_id == "env-var-1"
    assert env_var.environment_id == "env-1"
    assert env_var.var_key == "token"
    assert env_var.value == "abc"


@pytest.mark.asyncio
async def test_api_case_run_persists_rendered_request_snapshot():
    class FakeApiCaseRepository:
        session = AuthorizationDatabase(environment=True)

        def __init__(self):
            self.rows = []
            self.api_case = SimpleNamespace(
                case_id="case-1",
                collection_id="collection-1",
                method="GET",
                url_template="/ping/{{token}}",
                headers_json={"X-Token": "{{token}}"},
                query_json={},
                body_type="none",
                body_json=None,
                body_text="",
                timeout_ms=1000,
            )
            self.collection = SimpleNamespace(
                collection_id="collection-1",
                requirement_id="requirement-1",
            )
            self.requirement = SimpleNamespace(
                requirement_id="requirement-1",
                sprint_id="sprint-1",
            )
            self.sprint = SimpleNamespace(sprint_id="sprint-1", project_id="project-1")
            self.project = SimpleNamespace(project_id="project-1", user_id="user-1")
            self.environment = SimpleNamespace(
                environment_id="env-1",
                project_id="project-1",
                kind="api",
                base_url="https://api.example.test",
            )

        async def get_case(self, case_id):
            return self.api_case

        async def get_collection(self, collection_id):
            return self.collection

        async def get_requirement(self, requirement_id):
            return self.requirement

        async def get_sprint(self, sprint_id):
            return self.sprint

        async def get_project(self, project_id):
            return self.project

        async def get_environment(self, environment_id):
            return self.environment

        async def list_environment_vars(self, environment_id):
            return [SimpleNamespace(var_key="token", value="abc")]

        def add_all(self, rows):
            self.rows.extend(rows)

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    repository = FakeApiCaseRepository()
    service = ApiCaseService(repository)

    await service.run("user-1", "case-1", RunApiCaseRequest(environmentId="env-1"))

    run = next(row for row in repository.rows if hasattr(row, "request_snapshot_json"))
    assert run.request_snapshot_json == {
        "method": "GET",
        "url": "https://api.example.test/ping/abc",
        "headersJson": '{"X-Token":"abc"}',
        "queryJson": "{}",
        "bodyType": "none",
        "body": "",
    }
    assert run.runtime_vars_json == {"token": "abc"}


@pytest.mark.asyncio
async def test_api_case_run_response_uses_go_pending_worker_contract():
    class FakeApiCaseRepository:
        session = AuthorizationDatabase(environment=True)

        def __init__(self):
            self.rows = []
            self.api_case = SimpleNamespace(
                case_id="case-1",
                collection_id="collection-1",
                method="GET",
                url_template="/ping",
                headers_json={},
                query_json={},
                body_type="none",
                body_json=None,
                body_text="",
                timeout_ms=1000,
            )
            self.collection = SimpleNamespace(
                collection_id="collection-1",
                requirement_id="requirement-1",
            )
            self.requirement = SimpleNamespace(
                requirement_id="requirement-1",
                sprint_id="sprint-1",
            )
            self.sprint = SimpleNamespace(sprint_id="sprint-1", project_id="project-1")
            self.project = SimpleNamespace(project_id="project-1", user_id="user-1")
            self.environment = SimpleNamespace(
                environment_id="env-1",
                project_id="project-1",
                kind="api",
                base_url="https://api.example.test",
            )

        async def get_case(self, case_id):
            return self.api_case

        async def get_collection(self, collection_id):
            return self.collection

        async def get_requirement(self, requirement_id):
            return self.requirement

        async def get_sprint(self, sprint_id):
            return self.sprint

        async def get_project(self, project_id):
            return self.project

        async def get_environment(self, environment_id):
            return self.environment

        async def list_environment_vars(self, environment_id):
            return [SimpleNamespace(var_key="token", value="abc")]

        def add_all(self, rows):
            self.rows.extend(rows)

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    service = ApiCaseService(FakeApiCaseRepository())

    payload = await service.run("user-1", "case-1", RunApiCaseRequest(environmentId="env-1"))

    assert payload["status"] == "pending"
    assert payload["runtimeVarsJson"] == '{"token":"abc"}'
    assert payload["response"] == {"statusCode": 0, "headersJson": "{}", "body": ""}


@pytest.mark.asyncio
async def test_api_collection_run_response_uses_go_pending_worker_contract():
    class FakeApiCollectionRunRepository:
        session = AuthorizationDatabase(environment=True)

        def __init__(self):
            self.rows = []
            self.collection = SimpleNamespace(
                collection_id="collection-1",
                requirement_id="requirement-1",
            )
            self.requirement = SimpleNamespace(
                requirement_id="requirement-1",
                sprint_id="sprint-1",
            )
            self.sprint = SimpleNamespace(sprint_id="sprint-1", project_id="project-1")
            self.project = SimpleNamespace(project_id="project-1", user_id="user-1")
            self.environment = SimpleNamespace(
                environment_id="env-1",
                project_id="project-1",
                kind="api",
                base_url="https://api.example.test",
            )
            self.cases = [SimpleNamespace(case_id="case-1", order_no=1, continue_on_failure=False)]

        async def get_collection(self, collection_id):
            return self.collection

        async def get_requirement(self, requirement_id):
            return self.requirement

        async def get_sprint(self, sprint_id):
            return self.sprint

        async def get_project(self, project_id):
            return self.project

        async def get_environment(self, environment_id):
            return self.environment

        async def list_environment_vars(self, environment_id):
            return [SimpleNamespace(var_key="token", value="abc")]

        async def list_cases(self, collection_id):
            return self.cases

        def add_all(self, rows):
            self.rows.extend(rows)

        def add(self, row):
            self.rows.append(row)

        async def flush(self):
            return None

        async def commit(self):
            return None

        async def refresh(self, row):
            return None

    repository = FakeApiCollectionRunRepository()
    service = ApiCollectionRunService(repository)

    payload = await service.run(
        "user-1",
        "collection-1",
        RunApiCaseRequest(environmentId="env-1"),
    )
    assert payload["status"] == "pending"
    assert payload["runtimeVarsJson"] == "{}"


@pytest.mark.asyncio
async def test_api_collection_run_report_includes_case_run_details():
    run = SimpleNamespace(
        collection_run_id="collection-run-1",
        collection_id="collection-1",
        requirement_id="requirement-1",
        sprint_id="sprint-1",
        project_id="project-1",
        environment_id="env-1",
        trigger_user_id="user-1",
        trigger_type="manual",
        status="success",
        total_count=1,
        success_count=1,
        failed_count=0,
        error_count=0,
        skipped_count=0,
        runtime_vars_json={"token": "abc"},
        error_message="",
        started_at=None,
        finished_at=None,
        duration_ms=1000,
        created_at=None,
        updated_at=None,
    )
    item = SimpleNamespace(
        item_id="item-1",
        case_id="case-1",
        case_run_id="case-run-1",
        order_no=1,
        status="success",
        continue_on_failure=False,
        error_message="",
        started_at=None,
        finished_at=None,
        duration_ms=1000,
    )
    case = SimpleNamespace(case_id="case-1", name="Ping")
    case_run = SimpleNamespace(
        run_id="case-run-1",
        request_snapshot_json={"method": "GET", "url": "https://api.example.test/ping"},
        response_snapshot_json={"statusCode": 200, "body": "ok"},
        runtime_vars_json={"token": "abc"},
        extract_results_json=[{"success": True}],
        assert_results_json=[{"success": True}],
    )

    class FakeApiCollectionRunRepository:
        session = AuthorizationDatabase()

        async def get_run(self, collection_run_id):
            return run

        async def get_run_scope(self, run):
            return {
                "requirement_id": "requirement-1",
                "sprint_id": "sprint-1",
                "project_id": "project-1",
            }

        async def get_project(self, project_id):
            return SimpleNamespace(project_id="project-1", user_id="user-1")

        async def list_items(self, collection_run_id):
            return [item]

        async def report_cases(self, case_ids):
            return {case.case_id: case}

        async def report_case_runs(self, run_ids):
            return {case_run.run_id: case_run}

    service = ApiCollectionRunService(FakeApiCollectionRunRepository())

    report = await service.report("user-1", "collection-run-1")

    assert report["items"] == [
        {
            "itemId": "item-1",
            "caseId": "case-1",
            "caseRunId": "case-run-1",
            "caseName": "Ping",
            "orderNo": 1,
            "status": "success",
            "continueOnFailure": False,
            "errorMessage": "",
            "startedAt": "",
            "finishedAt": "",
            "durationMs": 1000,
            "request": {"method": "GET", "url": "https://api.example.test/ping"},
            "response": {"statusCode": 200, "body": "ok"},
            "runtimeVarsJson": '{"token":"abc"}',
            "extractResults": [{"success": True}],
            "assertResults": [{"success": True}],
        }
    ]


@pytest.mark.asyncio
async def test_api_worker_snapshot_returns_go_case_run_request_payload():
    task = SimpleNamespace(
        task_id="task-1",
        task_type="api_case_debug",
        domain="api",
        run_id="run-1",
        suite_id="",
        case_id="case-1",
        collection_run_id="",
        collection_id="collection-1",
        generate_task_id="",
        status="claimed",
    )
    run = SimpleNamespace(
        run_id="run-1",
        collection_run_id=None,
        collection_id="collection-1",
        case_id="case-1",
        environment_id="env-1",
        request_snapshot_json={
            "method": "GET",
            "url": "https://api.example.test/ping",
            "headersJson": "{}",
            "queryJson": "{}",
            "bodyType": "none",
            "body": "",
        },
        runtime_vars_json={"token": "abc"},
    )

    class EmptyScalars:
        def all(self):
            return []

    class FakeSession:
        async def scalar(self, statement):
            return run

        async def scalars(self, statement):
            return EmptyScalars()

    from testing_agent.domain.worker_context import ApiWorkerContext

    payload = await worker.build_snapshot(
        FakeSession(), "api", task, context=ApiWorkerContext("case-1", "collection-1", None)
    )

    assert payload == {
        "taskType": "api_case_debug",
        "caseRun": {
            "taskId": "task-1",
            "runId": "run-1",
            "collectionId": "collection-1",
            "caseId": "case-1",
            "environmentId": "env-1",
            "request": {
                "method": "GET",
                "url": "https://api.example.test/ping",
                "headersJson": "{}",
                "queryJson": "{}",
                "bodyType": "none",
                "body": "",
            },
            "runtimeVarsJson": '{"token":"abc"}',
            "extractRules": [],
            "assertRules": [],
        },
    }
