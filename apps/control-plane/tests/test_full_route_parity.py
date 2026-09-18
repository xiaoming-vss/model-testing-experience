from pathlib import Path

from testing_agent.app import create_app


def go_path(path: str) -> str:
    replacements = {
        "assert_rule_id": "assertRuleId",
        "binding_id": "bindingId",
        "case_id": "caseId",
        "collection_id": "collectionId",
        "collection_run_id": "collectionRunId",
        "connection_id": "connectionId",
        "environment_id": "environmentId",
        "env_var_id": "envVarId",
        "extract_rule_id": "extractRuleId",
        "project_id": "projectId",
        "remote_execution_id": "remoteExecutionId",
        "remote_project_id": "remoteProjectId",
        "requirement_id": "requirementId",
        "run_id": "runId",
        "skill_space_id": "skillSpaceId",
        "snapshot_date": "snapshotDate",
        "sprint_id": "sprintId",
        "suite_id": "suiteId",
        "suite_run_id": "suiteRunId",
        "task_id": "taskId",
    }
    for snake, camel in replacements.items():
        path = path.replace("{" + snake + "}", "{" + camel + "}")
    return path


def route_set():
    app = create_app()
    result = set()
    for path, methods in app.openapi()["paths"].items():
        for method in methods:
            result.add((method.upper(), path))
    return result


def test_missing_go_routes_are_exposed():
    routes = route_set()

    expected = {
        ("GET", "/v1/api-environments/{environment_id}"),
        ("PATCH", "/v1/api-environments/{environment_id}"),
        ("DELETE", "/v1/api-environments/{environment_id}"),
        ("POST", "/v1/api-environments/{environment_id}/vars"),
        ("GET", "/v1/api-environments/{environment_id}/vars"),
        ("GET", "/v1/api-environment-vars/{env_var_id}"),
        ("PATCH", "/v1/api-environment-vars/{env_var_id}"),
        ("DELETE", "/v1/api-environment-vars/{env_var_id}"),
        ("POST", "/v1/api-cases/{case_id}/assert-rules"),
        ("GET", "/v1/api-cases/{case_id}/assert-rules"),
        ("GET", "/v1/api-assert-rules/{assert_rule_id}"),
        ("PATCH", "/v1/api-assert-rules/{assert_rule_id}"),
        ("DELETE", "/v1/api-assert-rules/{assert_rule_id}"),
        ("POST", "/v1/api-cases/{case_id}/extract-rules"),
        ("GET", "/v1/api-cases/{case_id}/extract-rules"),
        ("GET", "/v1/api-extract-rules/{extract_rule_id}"),
        ("PATCH", "/v1/api-extract-rules/{extract_rule_id}"),
        ("DELETE", "/v1/api-extract-rules/{extract_rule_id}"),
        ("POST", "/v1/api-collections/{collection_id}/import"),
        ("GET", "/v1/ui-test-suites/{suite_id}"),
        ("PATCH", "/v1/ui-test-suites/{suite_id}"),
        ("DELETE", "/v1/ui-test-suites/{suite_id}"),
        ("POST", "/v1/ui-test-suites/{suite_id}/import"),
        ("GET", "/v1/ui-test-cases/{case_id}"),
        ("PATCH", "/v1/ui-test-cases/{case_id}"),
        ("DELETE", "/v1/ui-test-cases/{case_id}"),
        ("POST", "/v1/function-test-suites/{suite_id}/cases/import"),
        ("POST", "/v1/function-test-suites/{suite_id}/zentao/testcases/import"),
        ("GET", "/v1/integrations/zentao/connections"),
        ("GET", "/v1/integrations/zentao/connections/{connection_id}"),
        ("PATCH", "/v1/integrations/zentao/connections/{connection_id}"),
        ("DELETE", "/v1/integrations/zentao/connections/{connection_id}"),
        ("POST", "/v1/integrations/zentao/connections/{connection_id}/reauth"),
        ("GET", "/v1/integrations/zentao/connections/{connection_id}/projects"),
        (
            "GET",
            "/v1/integrations/zentao/connections/{connection_id}/projects/{remote_project_id}/executions",
        ),
        (
            "GET",
            "/v1/integrations/zentao/connections/{connection_id}/executions/{remote_execution_id}/testtasks",
        ),
        (
            "GET",
            "/v1/integrations/zentao/connections/{connection_id}/executions/{remote_execution_id}/stories",
        ),
        (
            "GET",
            "/v1/integrations/zentao/connections/{connection_id}/executions/{remote_execution_id}/cases",
        ),
        ("GET", "/v1/integrations/llm/connections"),
        ("POST", "/v1/integrations/llm/connections"),
        ("GET", "/v1/integrations/llm/connections/{connection_id}"),
        ("PATCH", "/v1/integrations/llm/connections/{connection_id}"),
        ("DELETE", "/v1/integrations/llm/connections/{connection_id}"),
        ("GET", "/v1/projects/{project_id}/integrations/zentao/connections"),
        ("POST", "/v1/projects/{project_id}/integrations/zentao/connections"),
        (
            "GET",
            "/v1/projects/{project_id}/integrations/zentao/connections/{connection_id}",
        ),
        (
            "PATCH",
            "/v1/projects/{project_id}/integrations/zentao/connections/{connection_id}",
        ),
        (
            "DELETE",
            "/v1/projects/{project_id}/integrations/zentao/connections/{connection_id}",
        ),
        (
            "POST",
            "/v1/projects/{project_id}/integrations/zentao/connections/{connection_id}/reauth",
        ),
        (
            "GET",
            "/v1/projects/{project_id}/integrations/zentao/connections/{connection_id}/projects",
        ),
        (
            "GET",
            "/v1/projects/{project_id}/integrations/zentao/connections/{connection_id}/projects/{remote_project_id}/executions",
        ),
        (
            "GET",
            "/v1/projects/{project_id}/integrations/zentao/connections/{connection_id}/executions/{remote_execution_id}/testtasks",
        ),
        (
            "GET",
            "/v1/projects/{project_id}/integrations/zentao/connections/{connection_id}/executions/{remote_execution_id}/stories",
        ),
        (
            "GET",
            "/v1/projects/{project_id}/integrations/zentao/connections/{connection_id}/executions/{remote_execution_id}/cases",
        ),
        ("GET", "/v1/projects/{project_id}/integrations/llm/connections"),
        ("POST", "/v1/projects/{project_id}/integrations/llm/connections"),
        (
            "GET",
            "/v1/projects/{project_id}/integrations/llm/connections/{connection_id}",
        ),
        (
            "PATCH",
            "/v1/projects/{project_id}/integrations/llm/connections/{connection_id}",
        ),
        (
            "DELETE",
            "/v1/projects/{project_id}/integrations/llm/connections/{connection_id}",
        ),
        ("POST", "/v1/projects/{project_id}/bindings"),
        ("GET", "/v1/projects/{project_id}/bindings"),
        ("DELETE", "/v1/projects/{project_id}/bindings/{binding_id}"),
        ("POST", "/v1/sprints/{sprint_id}/bindings"),
        ("GET", "/v1/sprints/{sprint_id}/bindings"),
        ("DELETE", "/v1/sprints/{sprint_id}/bindings/{binding_id}"),
        ("POST", "/v1/requirements/{requirement_id}/bindings"),
        ("GET", "/v1/requirements/{requirement_id}/bindings"),
        ("DELETE", "/v1/requirements/{requirement_id}/bindings/{binding_id}"),
        ("GET", "/v1/sprints/{sprint_id}/daily-metrics"),
        ("GET", "/v1/sprints/{sprint_id}/daily-metrics/{snapshot_date}"),
        ("PUT", "/v1/sprints/{sprint_id}/daily-metrics/{snapshot_date}"),
        ("GET", "/v1/projects/{project_id}/skills"),
        ("POST", "/v1/projects/{project_id}/skills"),
        ("DELETE", "/v1/projects/{project_id}/skills/{skill_space_id}"),
        ("GET", "/v1/projects/{project_id}/skills/{skill_space_id}/download"),
        ("GET", "/v1/projects/{project_id}/api-case-generate-tasks"),
        ("POST", "/v1/projects/{project_id}/api-case-generate-tasks"),
        ("GET", "/v1/api-case-generate-tasks/{task_id}"),
        ("PATCH", "/v1/api-case-generate-tasks/{task_id}"),
        ("DELETE", "/v1/api-case-generate-tasks/{task_id}"),
        ("POST", "/v1/api-case-generate-tasks/{task_id}/run"),
        ("GET", "/v1/api-case-generate-tasks/{task_id}/runs"),
        ("GET", "/v1/api-case-generate-task-runs/{run_id}"),
        ("POST", "/v1/api-case-generate-task-runs/{run_id}/review"),
        ("GET", "/v1/projects/{project_id}/function-case-generate-tasks"),
        ("POST", "/v1/projects/{project_id}/function-case-generate-tasks"),
        ("GET", "/v1/function-case-generate-tasks/{task_id}"),
        ("PATCH", "/v1/function-case-generate-tasks/{task_id}"),
        ("DELETE", "/v1/function-case-generate-tasks/{task_id}"),
        ("POST", "/v1/function-case-generate-tasks/{task_id}/run"),
        ("GET", "/v1/function-case-generate-tasks/{task_id}/runs"),
        ("GET", "/v1/function-case-generate-task-runs/{run_id}"),
        ("PATCH", "/v1/function-case-generate-task-runs/{run_id}/stage-output"),
        ("POST", "/v1/function-case-generate-task-runs/{run_id}/stage-review"),
        ("POST", "/v1/function-case-generate-task-runs/{run_id}/stage-retry"),
        ("POST", "/v1/function-case-generate-task-runs/{run_id}/review"),
        ("GET", "/v1/projects/{project_id}/requirement-analysis-tasks"),
        ("POST", "/v1/projects/{project_id}/requirement-analysis-tasks"),
        ("GET", "/v1/requirement-analysis-tasks/{task_id}"),
        ("PATCH", "/v1/requirement-analysis-tasks/{task_id}"),
        ("DELETE", "/v1/requirement-analysis-tasks/{task_id}"),
        ("POST", "/v1/requirement-analysis-tasks/{task_id}/run"),
        ("GET", "/v1/requirement-analysis-tasks/{task_id}/runs"),
        ("GET", "/v1/requirement-analysis-runs/{run_id}"),
        ("PATCH", "/v1/requirement-analysis-runs/{run_id}/stage-output"),
        ("POST", "/v1/requirement-analysis-runs/{run_id}/stage-review"),
        ("POST", "/v1/requirement-analysis-runs/{run_id}/stage-revise"),
        ("POST", "/v1/projects/{project_id}/test-report-generate-runs"),
        ("GET", "/v1/projects/{project_id}/test-report-generate-runs"),
        ("GET", "/v1/test-report-generate-runs/{run_id}"),
        ("GET", "/v1/test-report-generate-runs/{run_id}/pdf"),
    }

    expected = {(method, go_path(path)) for method, path in expected}

    assert expected <= routes
    assert ("POST", "/v1/integrations/zentao/connections") not in routes
    assert ("POST", "/v1/requirements/{requirementId}/analysis-runs") not in routes
    assert ("GET", "/v1/requirements/{requirementId}/analysis-runs") not in routes

    forbidden_test_report_task_routes = {
        ("GET", "/v1/projects/{projectId}/test-report-generate-tasks"),
        ("POST", "/v1/projects/{projectId}/test-report-generate-tasks"),
        ("GET", "/v1/test-report-generate-tasks/{taskId}"),
        ("PATCH", "/v1/test-report-generate-tasks/{taskId}"),
        ("DELETE", "/v1/test-report-generate-tasks/{taskId}"),
        ("POST", "/v1/test-report-generate-tasks/{taskId}/run"),
        ("GET", "/v1/test-report-generate-tasks/{taskId}/runs"),
        ("GET", "/v1/test-report-generate-task-runs/{runId}"),
    }
    leaked = sorted(route for route in forbidden_test_report_task_routes if route in routes)
    assert leaked == []


def test_v1_routes_do_not_return_bare_list_response_models():
    router_root = Path("src/testing_agent/routers")
    offenders = []
    for router_path in router_root.glob("*.py"):
        text = router_path.read_text(encoding="utf-8")
        if "ApiResponse[list[" in text:
            offenders.append(str(router_path))

    assert offenders == []
